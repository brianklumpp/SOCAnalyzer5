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
    password: Optional[str] = None  # PDF password for encrypted files
    
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
        data.setdefault('password', None)
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
                priority: int = 10,
                password: Optional[str] = None) -> int:
        """
        Add a scan to the queue.
        
        Args:
            job_id: Unique job identifier
            filename: Original PDF filename
            pdf_path: Path to saved PDF
            report_type: Optional report type (auto-detect if None)
            priority: Queue priority (0=highest, 10=normal, 99=lowest)
            password: Optional PDF password for encrypted files
            
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
            queued_at=datetime.now().isoformat(),
            password=password
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
    
    def get_status(self, max_scans: int = 50) -> Dict[str, Any]:
        """
        Get current queue state.
        
        Args:
            max_scans: Maximum number of scans to return (default 50 to prevent timeout)
        
        Returns:
            Complete queue status with all scans
        """
        import json
        
        try:
            stats = self.redis.hgetall(self.KEY_STATS)
            current_job_id = self.redis.get(self.KEY_CURRENT)
            queued_job_ids = self.redis.zrange(self.KEY_ACTIVE, 0, max_scans - 1)  # Limit to prevent timeout
        except Exception as e:
            logger.error(f"[QUEUE] Redis error getting queue status: {e}")
            return {
                "paused": False,
                "current_job_id": None,
                "queue_length": 0,
                "scans": [],
                "stats": {
                    "total_queued": 0,
                    "total_completed": 0,
                    "total_failed": 0,
                    "total_cancelled": 0
                }
            }
        
        # Load scan details
        scans = []
        
        # Currently running
        if current_job_id:
            try:
                scan = self._load_scan(current_job_id)  # Already a string
                if scan:
                    scan_dict = {
                        **scan.to_dict(),
                        "position": 0
                    }
                    # Enrich with job state (identified_entities, counters, etc.)
                    try:
                        from ..job_state import get_job_compat
                        job_data = get_job_compat(current_job_id, self.redis)
                        if job_data:
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
            except Exception as e:
                logger.error(f"[QUEUE] Error loading current scan {current_job_id}: {e}")
        
        # Queued scans (limited to max_scans)
        for i, job_id in enumerate(queued_job_ids):
            try:
                scan = self._load_scan(job_id)
                if scan:
                    scan_dict = {
                        **scan.to_dict(),
                        "position": i + 1
                    }
                    # Enrich with job state
                    try:
                        from ..job_state import get_job_compat
                        job_data = get_job_compat(job_id, self.redis)
                        if job_data:
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
            except Exception as e:
                logger.error(f"[QUEUE] Error loading queued scan {job_id}: {e}")
                continue
        
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
    
    def get_all(self) -> List[QueuedScan]:
        """Get all scans from cache and sync with Redis."""
        # Get all job IDs from Redis active queue
        job_ids = self.redis.zrange(self.KEY_ACTIVE, 0, -1)
        
        # Load scans that aren't in cache
        for job_id in job_ids:
            if job_id not in self._local_cache:
                scan = self._load_scan(job_id)
                if scan:
                    self._local_cache[job_id] = scan
        
        # Also check running scans (not in active queue)
        for scan in list(self._local_cache.values()):
            if scan.status == ScanQueueStatus.RUNNING:
                # Refresh from Redis to get latest state
                fresh_scan = self._load_scan(scan.job_id)
                if fresh_scan:
                    self._local_cache[scan.job_id] = fresh_scan
        
        return list(self._local_cache.values())
    
    def get_running_count(self) -> int:
        """Get count of currently running scans."""
        all_scans = self.get_all()
        running = [s for s in all_scans if s.status == ScanQueueStatus.RUNNING]
        return len(running)
    
    def can_start_new_scan(self) -> bool:
        """Check if we can start a new scan based on max_concurrent limit."""
        if self.is_paused():
            return False
        running_count = self.get_running_count()
        return running_count < self.max_concurrent


# Global queue instance (initialized in main.py)
scan_queue: Optional[ScanQueue] = None
_worker_thread: Optional['threading.Thread'] = None
_worker_stop_event: Optional['threading.Event'] = None


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


def _queue_worker():
    """
    Background worker that processes queued scans.
    Runs continuously and starts new scans when slots are available.
    """
    import threading
    import time
    
    logger.info("[QUEUE_WORKER] Starting queue worker thread")
    
    while not _worker_stop_event.is_set():
        try:
            queue = get_scan_queue()
            
            # Check if we can start new scans
            if queue.can_start_new_scan():
                # Get all queued scans
                all_scans = queue.get_all()
                queued_scans = [s for s in all_scans if s.status == ScanQueueStatus.QUEUED]
                
                # Sort by priority (lower number = higher priority)
                queued_scans.sort(key=lambda s: s.priority)
                
                # Start scans up to max_concurrent limit
                running_count = queue.get_running_count()
                slots_available = queue.max_concurrent - running_count
                
                for scan in queued_scans[:slots_available]:
                    try:
                        # Import here to avoid circular dependency
                        from ..main import run_analysis_job
                        
                        # Mark as running
                        scan.status = ScanQueueStatus.RUNNING
                        scan.started_at = datetime.now().isoformat()
                        queue._save_scan(scan)
                        
                        # Start processing thread
                        thread = threading.Thread(
                            target=run_analysis_job,
                            args=(scan.job_id, scan.pdf_path, scan.filename, scan.report_type, None, 1, False, scan.password),  # db=None, user_id=1, resume=False, password
                            name=f"ScanWorker-{scan.job_id[:8]}"
                        )
                        thread.daemon = True
                        thread.start()
                        
                        logger.info(f"[QUEUE_WORKER] Started scan {scan.filename} (job_id={scan.job_id})")
                        
                    except Exception as e:
                        logger.error(f"[QUEUE_WORKER] Failed to start scan {scan.job_id}: {e}")
                        scan.status = ScanQueueStatus.FAILED
                        scan.error = str(e)
                        queue._save_scan(scan)
            
            # Sleep before next check
            time.sleep(2)  # Check every 2 seconds
            
        except Exception as e:
            logger.error(f"[QUEUE_WORKER] Error in worker loop: {e}")
            time.sleep(5)  # Longer sleep on error
    
    logger.info("[QUEUE_WORKER] Queue worker stopped")


def start_queue_worker():
    """Start the background queue worker thread."""
    global _worker_thread, _worker_stop_event
    import threading
    
    if _worker_thread is not None and _worker_thread.is_alive():
        logger.warning("[QUEUE_WORKER] Worker thread already running")
        return
    
    _worker_stop_event = threading.Event()
    _worker_thread = threading.Thread(target=_queue_worker, name="QueueWorker", daemon=True)
    _worker_thread.start()
    logger.info("[QUEUE_WORKER] Queue worker thread started")


def stop_queue_worker():
    """Stop the background queue worker thread."""
    global _worker_stop_event
    
    if _worker_stop_event:
        logger.info("[QUEUE_WORKER] Stopping queue worker...")
        _worker_stop_event.set()
        if _worker_thread:
            _worker_thread.join(timeout=5)
        logger.info("[QUEUE_WORKER] Queue worker stopped")
