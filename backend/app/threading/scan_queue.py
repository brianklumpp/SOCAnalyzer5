"""
backend/app/threading/scan_queue.py

Multi-Scan Queue Manager for SOC Analyzer v2.1.0

Features:
- FIFO queue with priority override (urgent scans jump ahead)
- Pause/resume capability (user control)
- Persistent queue state (Redis-backed)
- Batch upload support (10+ PDFs at once)
- Position tracking for frontend display
- Automatic progression (dequeue next scan when complete)
"""

import logging
import asyncio
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import redis

logger = logging.getLogger(__name__)


class ScanQueueStatus(Enum):
    """Scan status in queue."""
    QUEUED = "queued"       # Waiting to start
    RUNNING = "running"     # Currently processing
    PAUSED = "paused"       # User paused this scan
    COMPLETED = "completed" # Finished successfully
    FAILED = "failed"       # Extraction failed
    CANCELLED = "cancelled" # User cancelled


@dataclass
class QueuedScan:
    """Metadata for a queued scan."""
    job_id: str
    filename: str
    pdf_path: str
    report_type: Optional[str]
    priority: int  # 0 = highest, 10 = normal, 99 = lowest
    status: ScanQueueStatus
    queued_at: str  # ISO format timestamp
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['status'] = self.status.value
        # Filter out None values for Redis compatibility
        return {k: v for k, v in data.items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueuedScan':
        """Create from dictionary."""
        data['status'] = ScanQueueStatus(data['status'])
        # Set defaults for missing optional fields
        data.setdefault('report_type', None)
        data.setdefault('started_at', None)
        data.setdefault('completed_at', None)
        data.setdefault('error', None)
        return cls(**data)


class ScanQueue:
    """
    Multi-scan queue manager with priority scheduling.
    
    Features:
    - FIFO queue with priority override
    - Pause/resume capability
    - Persistent queue state (Redis)
    - Batch upload support
    - Automatic progression
    """
    
    # Redis key patterns
    KEY_ACTIVE = "scan_queue:active"           # Sorted set: {job_id: priority}
    KEY_CURRENT = "scan_queue:current"         # String: currently running job_id
    KEY_PAUSED = "scan_queue:paused"           # Boolean: queue pause state
    KEY_STATS = "scan_queue:stats"             # Hash: queue statistics
    KEY_SCAN_PREFIX = "scan_queue:scan:"       # Hash: scan metadata per job_id
    
    def __init__(self, redis_client: redis.Redis, max_concurrent: int = 1):
        """
        Initialize scan queue manager.
        
        Args:
            redis_client: Redis connection for persistence
            max_concurrent: Maximum concurrent scans (default: 1, future: 2-3)
        """
        self.redis = redis_client
        self.max_concurrent = max_concurrent
        self._local_cache: Dict[str, QueuedScan] = {}  # Local cache for performance
        
        logger.info(f"[QUEUE] Initialized with max_concurrent={max_concurrent}")
        
        # Initialize stats if not exist
        if not self.redis.exists(self.KEY_STATS):
            self.redis.hset(self.KEY_STATS, mapping={
                "total_queued": "0",
                "total_completed": "0",
                "total_failed": "0",
                "total_cancelled": "0"
            })
    
    def enqueue(self, 
                job_id: str,
                filename: str,
                pdf_path: str,
                report_type: Optional[str] = None,
                priority: int = 10) -> int:
        """
        Add a scan to the queue.
        
        Args:
            job_id: Unique job identifier
            filename: Original PDF filename
            pdf_path: Path to saved PDF
            report_type: Optional report type (auto-detect if None)
            priority: Queue priority (0=highest, 10=normal, 99=lowest)
            
        Returns:
            Queue position (0 = will start immediately)
        """
        scan = QueuedScan(
            job_id=job_id,
            filename=filename,
            pdf_path=pdf_path,
            report_type=report_type,
            priority=priority,
            status=ScanQueueStatus.QUEUED,
            queued_at=datetime.now().isoformat()
        )
        
        # Store scan metadata in Redis
        scan_key = f"{self.KEY_SCAN_PREFIX}{job_id}"
        self.redis.hset(scan_key, mapping=scan.to_dict())
        self.redis.expire(scan_key, 86400 * 7)  # 7 day TTL
        
        # Add to sorted set (sorted by priority, then timestamp)
        # Score = priority * 1e10 + timestamp (allows FIFO within same priority)
        timestamp = datetime.now().timestamp()
        score = priority * 1e10 + timestamp
        self.redis.zadd(self.KEY_ACTIVE, {job_id: score})
        
        # Update stats
        self.redis.hincrby(self.KEY_STATS, "total_queued", 1)
        
        # Cache locally
        self._local_cache[job_id] = scan
        
        position = self.get_position(job_id)
        logger.info(f"[QUEUE] Added {filename} (job_id={job_id}, position={position}, priority={priority})")
        
        return position
    
    def dequeue(self) -> Optional[QueuedScan]:
        """
        Get next scan from queue (respects pause state).
        
        Returns:
            Next scan to process, or None if queue paused/empty
        """
        # Check if paused
        if self.is_paused():
            logger.debug("[QUEUE] Queue is paused, not dequeueing")
            return None
        
        # Check if already at max concurrent
        current_job_id = self.redis.get(self.KEY_CURRENT)
        if current_job_id:
            logger.debug(f"[QUEUE] Already processing job {current_job_id}")
            return None
        
        # Get highest priority scan (lowest score)
        result = self.redis.zrange(self.KEY_ACTIVE, 0, 0, withscores=True)
        if not result:
            logger.debug("[QUEUE] Queue is empty")
            return None
        
        job_id = result[0][0]
        
        # Remove from active queue
        self.redis.zrem(self.KEY_ACTIVE, job_id)
        
        # Mark as current
        self.redis.set(self.KEY_CURRENT, job_id, ex=86400)  # 24h TTL
        
        # Load scan metadata
        scan = self._load_scan(job_id)
        if scan:
            scan.status = ScanQueueStatus.RUNNING
            scan.started_at = datetime.now().isoformat()
            self._save_scan(scan)
            
            logger.info(f"[QUEUE] Dequeued {scan.filename} (job_id={job_id})")
            return scan
        
        return None
    
    def mark_complete(self, job_id: str, error: Optional[str] = None):
        """
        Mark scan as complete or failed.
        
        Args:
            job_id: Job to mark complete
            error: Optional error message (if failed)
        """
        # Remove from current
        current = self.redis.get(self.KEY_CURRENT)
        if current and current == job_id:
            self.redis.delete(self.KEY_CURRENT)
        
        # Update scan status
        scan = self._load_scan(job_id)
        if scan:
            scan.completed_at = datetime.now().isoformat()
            if error:
                scan.status = ScanQueueStatus.FAILED
                scan.error = error
                self.redis.hincrby(self.KEY_STATS, "total_failed", 1)
                logger.error(f"[QUEUE] Scan {job_id} failed: {error}")
            else:
                scan.status = ScanQueueStatus.COMPLETED
                self.redis.hincrby(self.KEY_STATS, "total_completed", 1)
                logger.info(f"[QUEUE] Scan {job_id} completed successfully")
            
            self._save_scan(scan)
        
        # Remove from local cache
        self._local_cache.pop(job_id, None)
    
    def cancel(self, job_id: str):
        """
        Cancel a scan (remove from queue or stop if running).
        
        Args:
            job_id: Job to cancel
        """
        # Remove from active queue
        removed = self.redis.zrem(self.KEY_ACTIVE, job_id)
        
        # Check if currently running
        current = self.redis.get(self.KEY_CURRENT)
        is_running = current and current == job_id
        
        if is_running:
            # Signal cancellation (existing mechanism)
            self.redis.set(f"job:{job_id}:cancelled", "true", ex=3600)
            self.redis.delete(self.KEY_CURRENT)
            logger.info(f"[QUEUE] Cancelled running scan {job_id}")
        elif removed:
            logger.info(f"[QUEUE] Removed queued scan {job_id}")
        
        # Update scan status
        scan = self._load_scan(job_id)
        if scan:
            scan.status = ScanQueueStatus.CANCELLED
            scan.completed_at = datetime.now().isoformat()
            self._save_scan(scan)
            self.redis.hincrby(self.KEY_STATS, "total_cancelled", 1)
        
        # Remove from local cache
        self._local_cache.pop(job_id, None)
    
    def reprioritize(self, job_id: str, new_priority: int):
        """
        Change scan priority (moves position in queue).
        
        Args:
            job_id: Scan to reprioritize
            new_priority: New priority (0=highest)
        """
        # Check if in queue
        score = self.redis.zscore(self.KEY_ACTIVE, job_id)
        if score is None:
            logger.warning(f"[QUEUE] Cannot reprioritize {job_id} - not in queue")
            return
        
        # Update priority (keep original timestamp for FIFO within priority)
        old_priority = int(score / 1e10)
        timestamp = score - (old_priority * 1e10)
        new_score = new_priority * 1e10 + timestamp
        
        self.redis.zadd(self.KEY_ACTIVE, {job_id: new_score})
        
        # Update scan metadata
        scan = self._load_scan(job_id)
        if scan:
            scan.priority = new_priority
            self._save_scan(scan)
        
        new_position = self.get_position(job_id)
        logger.info(f"[QUEUE] Reprioritized {job_id}: {old_priority} → {new_priority} (position: {new_position})")
    
    def pause(self):
        """Pause queue processing (current scan continues, next doesn't start)."""
        self.redis.set(self.KEY_PAUSED, "true")
        logger.info("[QUEUE] Queue paused")
    
    def resume(self):
        """Resume queue processing."""
        self.redis.delete(self.KEY_PAUSED)
        logger.info("[QUEUE] Queue resumed")
    
    def is_paused(self) -> bool:
        """Check if queue is paused."""
        return self.redis.exists(self.KEY_PAUSED) > 0
    
    def get_position(self, job_id: str) -> int:
        """
        Get position in queue.
        
        Returns:
            0 = currently running, 1+ = queued position, -1 = not found
        """
        # Check if currently running
        current = self.redis.get(self.KEY_CURRENT)
        if current and current == job_id:
            return 0
        
        # Get position in sorted set
        rank = self.redis.zrank(self.KEY_ACTIVE, job_id)
        if rank is not None:
            return rank + 1  # 1-indexed for user display
        
        return -1
    
    def is_running(self, job_id: str) -> bool:
        """Check if scan is currently running."""
        current = self.redis.get(self.KEY_CURRENT)
        return current and current == job_id
    
    def get_active_job_ids(self) -> List[str]:
        """Get all active job IDs (running + queued)."""
        job_ids = []
        
        # Currently running
        current = self.redis.get(self.KEY_CURRENT)
        if current:
            job_ids.append(current)
        
        # Queued
        queued = self.redis.zrange(self.KEY_ACTIVE, 0, -1)
        job_ids.extend(queued)
        
        return job_ids
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current queue state.
        
        Returns:
            Complete queue status with all scans
        """
        import json
        
        stats = self.redis.hgetall(self.KEY_STATS)
        current_job_id = self.redis.get(self.KEY_CURRENT)
        queued_job_ids = self.redis.zrange(self.KEY_ACTIVE, 0, -1)  # Already strings with decode_responses=True
        
        # Load scan details
        scans = []
        
        # Currently running
        if current_job_id:
            scan = self._load_scan(current_job_id)  # Already a string
            if scan:
                scan_dict = {
                    **scan.to_dict(),
                    "position": 0
                }
                # Enrich with job state (identified_entities, counters, etc.)
                job_state = self.redis.get(f"job:{current_job_id}")
                if job_state:
                    try:
                        job_data = json.loads(job_state)
                        # Add identified_entities for queue card display
                        if "identified_entities" in job_data:
                            scan_dict["identifiedEntities"] = job_data["identified_entities"]
                        # Add counters for progress display
                        if "counters" in job_data:
                            scan_dict["counters"] = job_data["counters"]
                        # Add detected subtype
                        if "detected_subtype" in job_data:
                            scan_dict["detectedSubtype"] = job_data["detected_subtype"]
                        # Add top-level fields for backward compatibility
                        if "logo_url" in job_data:
                            scan_dict["logo_url"] = job_data["logo_url"]
                        if "auditor" in job_data:
                            scan_dict["auditor"] = job_data["auditor"]
                    except Exception as e:
                        logger.warning(f"[QUEUE] Failed to enrich scan {current_job_id} with job state: {e}")
                scans.append(scan_dict)
        
        # Queued scans
        for i, job_id in enumerate(queued_job_ids):
            scan = self._load_scan(job_id)
            if scan:
                scan_dict = {
                    **scan.to_dict(),
                    "position": i + 1
                }
                # Enrich with job state
                job_state = self.redis.get(f"job:{job_id}")
                if job_state:
                    try:
                        job_data = json.loads(job_state)
                        if "identified_entities" in job_data:
                            scan_dict["identifiedEntities"] = job_data["identified_entities"]
                        if "counters" in job_data:
                            scan_dict["counters"] = job_data["counters"]
                        if "detected_subtype" in job_data:
                            scan_dict["detectedSubtype"] = job_data["detected_subtype"]
                        if "logo_url" in job_data:
                            scan_dict["logo_url"] = job_data["logo_url"]
                        if "auditor" in job_data:
                            scan_dict["auditor"] = job_data["auditor"]
                    except Exception as e:
                        logger.warning(f"[QUEUE] Failed to enrich scan {job_id} with job state: {e}")
                scans.append(scan_dict)
        
        return {
            "paused": self.is_paused(),
            "current_job_id": current_job_id if current_job_id else None,  # Already a string
            "queue_length": len(queued_job_ids),
            "scans": scans,
            "stats": {
                "total_queued": int(stats.get("total_queued", 0)),  # String keys with decode_responses=True
                "total_completed": int(stats.get("total_completed", 0)),
                "total_failed": int(stats.get("total_failed", 0)),
                "total_cancelled": int(stats.get("total_cancelled", 0))
            }
        }
    
    def _load_scan(self, job_id: str) -> Optional[QueuedScan]:
        """Load scan metadata from Redis."""
        # Check local cache first
        if job_id in self._local_cache:
            return self._local_cache[job_id]
        
        # Load from Redis
        scan_key = f"{self.KEY_SCAN_PREFIX}{job_id}"
        data = self.redis.hgetall(scan_key)
        
        if not data:
            return None
        
        # Data is already strings with decode_responses=True
        # No need to decode
        
        scan = QueuedScan.from_dict(data)
        self._local_cache[job_id] = scan
        return scan
    
    def _save_scan(self, scan: QueuedScan):
        """Save scan metadata to Redis."""
        scan_key = f"{self.KEY_SCAN_PREFIX}{scan.job_id}"
        self.redis.hset(scan_key, mapping=scan.to_dict())
        self.redis.expire(scan_key, 86400 * 7)  # 7 day TTL
        self._local_cache[scan.job_id] = scan


# Global queue instance (initialized in main.py)
scan_queue: Optional[ScanQueue] = None


def initialize_scan_queue(redis_client: redis.Redis, max_concurrent: int = 1):
    """Initialize the global scan queue instance."""
    global scan_queue
    scan_queue = ScanQueue(redis_client, max_concurrent)
    logger.info("[QUEUE] Global scan queue initialized")
    return scan_queue


def get_scan_queue() -> ScanQueue:
    """Get the global scan queue instance."""
    if scan_queue is None:
        raise RuntimeError("Scan queue not initialized. Call initialize_scan_queue() first.")
    return scan_queue
