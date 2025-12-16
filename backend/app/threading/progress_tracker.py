"""
backend/app/threading/progress_tracker.py

Enhanced Progress Tracker for SOC Analyzer v2.1.0

Features:
- Phase-level progress tracking (prerequisites, metadata, content, post-processing)
- Entity detection timing (company, auditor, logo, dates)
- Extraction rate calculations (controls/min, mappings/min)
- Granular updates (every 2 controls, every 4 mappings)
- Completion summaries with next steps
- CPU/memory monitoring
"""

import logging
import time
import psutil
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import redis

logger = logging.getLogger(__name__)


class PhaseStatus(Enum):
    """Phase execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractorStatus(Enum):
    """Extractor status within content phase."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PhaseStep:
    """Individual step within a phase."""
    name: str
    status: str = "pending"  # pending, running, done, failed
    duration_ms: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntityDetection:
    """Detected entity metadata."""
    name: str
    value: Any
    detected_at: float  # Unix timestamp
    confidence: Optional[float] = None
    logo_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "detected_at": self.detected_at,
            "confidence": self.confidence,
            "logo_url": self.logo_url
        }


@dataclass
class ExtractorProgress:
    """Progress for a specific extractor (controls, CUECs, suborgs)."""
    status: ExtractorStatus = ExtractorStatus.QUEUED
    progress: int = 0  # 0-100 percentage
    extracted_count: int = 0
    estimated_total: Optional[int] = None
    mapped_count: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    extraction_rate: float = 0.0  # items per minute
    mapping_rate: float = 0.0     # mappings per minute
    start_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "progress": self.progress,
            "extracted_count": self.extracted_count,
            "estimated_total": self.estimated_total,
            "mapped_count": self.mapped_count,
            "current_chunk": self.current_chunk,
            "total_chunks": self.total_chunks,
            "extraction_rate": round(self.extraction_rate, 2),
            "mapping_rate": round(self.mapping_rate, 2)
        }


@dataclass
class PhaseProgress:
    """Progress for a complete phase."""
    status: PhaseStatus = PhaseStatus.PENDING
    progress: int = 0  # 0-100 percentage
    duration_seconds: int = 0
    steps: List[PhaseStep] = field(default_factory=list)
    identified_entities: Dict[str, EntityDetection] = field(default_factory=dict)
    extractors: Dict[str, ExtractorProgress] = field(default_factory=dict)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "status": self.status.value,
            "progress": self.progress,
            "duration_seconds": self.duration_seconds
        }
        
        if self.steps:
            data["steps"] = [s.to_dict() for s in self.steps]
        
        if self.identified_entities:
            data["identified_entities"] = {
                k: v.to_dict() for k, v in self.identified_entities.items()
            }
        
        if self.extractors:
            data["extractors"] = {
                k: v.to_dict() for k, v in self.extractors.items()
            }
        
        return data


class ProgressTracker:
    """
    Enhanced progress tracker with phase-level visibility.
    
    Tracks:
    - Phase 1: Prerequisites (text extraction, section detection, report type)
    - Phase 2: Metadata (company, auditor, product, dates)
    - Phase 3: Content Extraction (controls, CUECs, subservice orgs)
    - Phase 4: Post-Processing (deduplication, DB upload, logo fetch)
    """
    
    def __init__(self, job_id: str, redis_client: redis.Redis):
        """
        Initialize progress tracker.
        
        Args:
            job_id: Job identifier
            redis_client: Redis connection for state persistence
        """
        self.job_id = job_id
        self.redis = redis_client
        self.overall_start_time = time.time()
        
        # Phase tracking
        self.phases = {
            "prerequisites": PhaseProgress(),
            "metadata": PhaseProgress(),
            "content_extraction": PhaseProgress(
                extractors={
                    "controls": ExtractorProgress(),
                    "cuecs": ExtractorProgress(),
                    "subservice_orgs": ExtractorProgress()
                }
            ),
            "post_processing": PhaseProgress()
        }
        
        self.current_phase = "prerequisites"
        
        # Stats tracking
        self.stats = {
            "elapsed_seconds": 0,
            "estimated_remaining_seconds": 0,
            "current_memory_mb": 0,
            "current_cpu_percent": 0,
            "thread_pool_active": 0,
            "thread_pool_queued": 0
        }
        
        # Completion data
        self.completion_summary: Optional[Dict[str, Any]] = None
        
        logger.info(f"[PROGRESS_TRACKER] Initialized for job {job_id}")
    
    # ==================== Phase Management ====================
    
    def start_phase(self, phase: str):
        """
        Start a new phase.
        
        Args:
            phase: Phase name (prerequisites, metadata, content_extraction, post_processing)
        """
        if phase not in self.phases:
            logger.warning(f"[PROGRESS_TRACKER] Unknown phase: {phase}")
            return
        
        self.current_phase = phase
        self.phases[phase].status = PhaseStatus.RUNNING
        self.phases[phase].start_time = time.time()
        
        logger.info(f"[PROGRESS_TRACKER] Phase '{phase}' started")
        self._publish_update()
    
    def complete_phase(self, phase: str, error: Optional[str] = None):
        """
        Mark phase as complete or failed.
        
        Args:
            phase: Phase name
            error: Optional error message (if failed)
        """
        if phase not in self.phases:
            return
        
        phase_data = self.phases[phase]
        phase_data.end_time = time.time()
        
        if phase_data.start_time:
            phase_data.duration_seconds = int(phase_data.end_time - phase_data.start_time)
        
        if error:
            phase_data.status = PhaseStatus.FAILED
            logger.error(f"[PROGRESS_TRACKER] Phase '{phase}' failed: {error}")
        else:
            phase_data.status = PhaseStatus.COMPLETED
            phase_data.progress = 100
            logger.info(f"[PROGRESS_TRACKER] Phase '{phase}' completed in {phase_data.duration_seconds}s")
        
        self._publish_update()
    
    # ==================== Phase Steps ====================
    
    def add_step(self, phase: str, step_name: str):
        """
        Add a step to a phase.
        
        Args:
            phase: Phase name
            step_name: Step name
        """
        if phase not in self.phases:
            return
        
        step = PhaseStep(name=step_name, status="running")
        self.phases[phase].steps.append(step)
        
        logger.debug(f"[PROGRESS_TRACKER] Added step '{step_name}' to phase '{phase}'")
    
    def complete_step(self, phase: str, step_name: str, duration_ms: int, error: Optional[str] = None):
        """
        Mark step as complete.
        
        Args:
            phase: Phase name
            step_name: Step name
            duration_ms: Step duration in milliseconds
            error: Optional error message
        """
        if phase not in self.phases:
            return
        
        for step in self.phases[phase].steps:
            if step.name == step_name:
                step.status = "failed" if error else "done"
                step.duration_ms = duration_ms
                step.error = error
                break
        
        logger.debug(f"[PROGRESS_TRACKER] Step '{step_name}' completed in {duration_ms}ms")
        self._publish_update()
    
    # ==================== Entity Detection ====================
    
    def update_entity(self, entity_type: str, value: Any, confidence: Optional[float] = None, logo_url: Optional[str] = None):
        """
        Update detected entity (shows immediately in UI).
        
        Args:
            entity_type: Entity type (company, auditor, product, report_date, coverage_period)
            value: Entity value
            confidence: Optional confidence score
            logo_url: Optional logo URL (for company)
        """
        entity = EntityDetection(
            name=entity_type,
            value=value,
            detected_at=time.time(),
            confidence=confidence,
            logo_url=logo_url
        )
        
        self.phases["metadata"].identified_entities[entity_type] = entity
        
        logger.info(f"[PROGRESS_TRACKER] Entity detected: {entity_type} = {value}")
        self._publish_update()
    
    # ==================== Control Extraction Progress ====================
    
    def start_extractor(self, extractor: str, estimated_total: Optional[int] = None, total_chunks: int = 0):
        """
        Start an extractor (controls, CUECs, suborgs).
        
        Args:
            extractor: Extractor name
            estimated_total: Estimated total items to extract
            total_chunks: Total number of chunks
        """
        if extractor not in self.phases["content_extraction"].extractors:
            return
        
        ext_data = self.phases["content_extraction"].extractors[extractor]
        ext_data.status = ExtractorStatus.RUNNING
        ext_data.estimated_total = estimated_total
        ext_data.total_chunks = total_chunks
        ext_data.start_time = time.time()
        
        logger.info(f"[PROGRESS_TRACKER] Extractor '{extractor}' started (est. {estimated_total} items, {total_chunks} chunks)")
        self._publish_update()
    
    def update_controls(self, count: int, estimated_total: Optional[int] = None):
        """
        Update control extraction count (called every 2 controls).
        
        Args:
            count: Current control count
            estimated_total: Optional updated estimate
        """
        self._update_extractor("controls", count, estimated_total)
    
    def update_mappings(self, count: int):
        """
        Update framework mapping count (called every 4 mappings).
        
        Args:
            count: Current mapping count
        """
        ext_data = self.phases["content_extraction"].extractors.get("controls")
        if not ext_data:
            return
        
        ext_data.mapped_count = count
        
        # Calculate mapping rate
        if ext_data.start_time:
            elapsed_min = (time.time() - ext_data.start_time) / 60.0
            if elapsed_min > 0:
                ext_data.mapping_rate = count / elapsed_min
        
        # Update progress percentage
        if ext_data.extracted_count > 0:
            ext_data.progress = int((count / ext_data.extracted_count) * 100)
        
        logger.debug(f"[PROGRESS_TRACKER] Mappings: {count} (rate: {ext_data.mapping_rate:.1f}/min)")
        self._publish_update()
    
    def update_cuecs(self, count: int, estimated_total: Optional[int] = None):
        """
        Update CUEC extraction count.
        
        Args:
            count: Current CUEC count
            estimated_total: Optional updated estimate
        """
        self._update_extractor("cuecs", count, estimated_total)
    
    def update_subservice_orgs(self, count: int):
        """
        Update subservice org count.
        
        Args:
            count: Current suborg count
        """
        self._update_extractor("subservice_orgs", count, None)
    
    def _update_extractor(self, extractor: str, count: int, estimated_total: Optional[int] = None):
        """
        Generic extractor update logic.
        
        Args:
            extractor: Extractor name
            count: Current item count
            estimated_total: Optional updated estimate
        """
        ext_data = self.phases["content_extraction"].extractors.get(extractor)
        if not ext_data:
            return
        
        ext_data.extracted_count = count
        
        if estimated_total:
            ext_data.estimated_total = estimated_total
        
        # Calculate extraction rate
        if ext_data.start_time:
            elapsed_min = (time.time() - ext_data.start_time) / 60.0
            if elapsed_min > 0:
                ext_data.extraction_rate = count / elapsed_min
        
        # Update progress percentage
        if ext_data.estimated_total and ext_data.estimated_total > 0:
            ext_data.progress = min(100, int((count / ext_data.estimated_total) * 100))
        
        logger.debug(f"[PROGRESS_TRACKER] {extractor}: {count}/{ext_data.estimated_total or '?'} (rate: {ext_data.extraction_rate:.1f}/min)")
        self._publish_update()
    
    def complete_extractor(self, extractor: str, error: Optional[str] = None):
        """
        Mark extractor as complete.
        
        Args:
            extractor: Extractor name
            error: Optional error message
        """
        ext_data = self.phases["content_extraction"].extractors.get(extractor)
        if not ext_data:
            return
        
        if error:
            ext_data.status = ExtractorStatus.FAILED
            logger.error(f"[PROGRESS_TRACKER] Extractor '{extractor}' failed: {error}")
        else:
            ext_data.status = ExtractorStatus.COMPLETED
            ext_data.progress = 100
            logger.info(f"[PROGRESS_TRACKER] Extractor '{extractor}' completed: {ext_data.extracted_count} items")
        
        self._publish_update()
    
    # ==================== Stats Monitoring ====================
    
    def update_stats(self):
        """Update CPU/memory stats (called periodically, e.g., every 5 seconds)."""
        try:
            self.stats["current_cpu_percent"] = int(psutil.cpu_percent(interval=0.1))
            self.stats["current_memory_mb"] = int(psutil.Process().memory_info().rss / 1024 / 1024)
        except Exception as e:
            logger.warning(f"[PROGRESS_TRACKER] Failed to update stats: {e}")
        
        # Calculate elapsed time
        self.stats["elapsed_seconds"] = int(time.time() - self.overall_start_time)
        
        # Estimate remaining time (rough calculation based on control extraction progress)
        controls = self.phases["content_extraction"].extractors.get("controls")
        if controls and controls.progress > 0 and controls.progress < 100:
            elapsed = self.stats["elapsed_seconds"]
            estimated_total = int((elapsed / controls.progress) * 100)
            self.stats["estimated_remaining_seconds"] = max(0, estimated_total - elapsed)
        
        self._publish_update()
    
    # ==================== Completion ====================
    
    def mark_complete(self, summary: Dict[str, Any]):
        """
        Mark scan as complete with summary.
        
        Args:
            summary: Completion summary with stats and next steps
        """
        self.completion_summary = {
            "status": "completed",
            "timestamp": time.time(),
            "duration_seconds": int(time.time() - self.overall_start_time),
            "summary": summary
        }
        
        logger.info(f"[PROGRESS_TRACKER] Scan complete: {summary}")
        self._publish_update()
    
    # ==================== Progress Calculation ====================
    
    def calculate_overall_progress(self) -> int:
        """
        Calculate overall progress (0-100).
        
        Phase weights:
        - Prerequisites: 20%
        - Metadata: 10%
        - Content Extraction: 65%
        - Post-Processing: 5%
        """
        weights = {
            "prerequisites": 0.20,
            "metadata": 0.10,
            "content_extraction": 0.65,
            "post_processing": 0.05
        }
        
        total_progress = 0.0
        
        for phase, weight in weights.items():
            phase_data = self.phases[phase]
            
            if phase == "content_extraction":
                # Average progress across extractors
                extractor_progress = []
                for ext_data in phase_data.extractors.values():
                    extractor_progress.append(ext_data.progress)
                
                if extractor_progress:
                    phase_progress = sum(extractor_progress) / len(extractor_progress)
                else:
                    phase_progress = 0
            else:
                phase_progress = phase_data.progress
            
            total_progress += phase_progress * weight
        
        return int(total_progress)
    
    # ==================== State Persistence ====================
    
    def _publish_update(self):
        """Publish progress update to Redis (for frontend polling)."""
        progress_data = {
            "job_id": self.job_id,
            "current_phase": self.current_phase,
            "overall_progress": self.calculate_overall_progress(),
            "phases": {
                phase: data.to_dict() for phase, data in self.phases.items()
            },
            "stats": self.stats
        }
        
        if self.completion_summary:
            progress_data["completion"] = self.completion_summary
        
        # Store in Redis (merge with existing job state)
        try:
            job_key = f"job:{self.job_id}"
            existing_data = self.redis.get(job_key)
            
            if existing_data:
                import json
                job_state = json.loads(existing_data)
                job_state["enhanced_progress"] = progress_data
                # Don't overwrite progress - let progress_callback handle it
                # job_state["progress"] = progress_data["overall_progress"]
                self.redis.set(job_key, json.dumps(job_state), ex=86400)
            else:
                # Create new job state
                self.redis.set(job_key, json.dumps(progress_data), ex=86400)
            
        except Exception as e:
            logger.error(f"[PROGRESS_TRACKER] Failed to publish update: {e}")
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get current progress state.
        
        Returns:
            Complete progress state
        """
        return {
            "job_id": self.job_id,
            "current_phase": self.current_phase,
            "overall_progress": self.calculate_overall_progress(),
            "phases": {
                phase: data.to_dict() for phase, data in self.phases.items()
            },
            "stats": self.stats,
            "completion": self.completion_summary
        }
