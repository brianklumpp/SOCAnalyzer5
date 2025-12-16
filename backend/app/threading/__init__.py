"""
Multi-threading infrastructure for SOC Analyzer v2.1.0

This package provides intelligent parallelism for scan processing with:
- Bounded resource usage (semaphore-based concurrency control)
- Adaptive throttling (CPU/memory monitoring)
- Circuit breaker pattern (graceful degradation)
- Scan queue management (priority scheduling, pause/resume)
- Enhanced progress tracking (phase-level visibility)
"""

from .intelligent_executor import (
    IntelligentTaskExecutor,
    TaskPriority,
    CircuitBreaker,
    AdaptiveThrottler
)
from .scan_queue import (
    ScanQueue,
    QueuedScan,
    ScanQueueStatus,
    initialize_scan_queue,
    get_scan_queue
)
from .progress_tracker import (
    ProgressTracker,
    PhaseStatus,
    ExtractorStatus,
    PhaseProgress,
    ExtractorProgress
)

__all__ = [
    'IntelligentTaskExecutor',
    'TaskPriority',
    'CircuitBreaker',
    'AdaptiveThrottler',
    'ScanQueue',
    'QueuedScan',
    'ScanQueueStatus',
    'initialize_scan_queue',
    'get_scan_queue',
    'ProgressTracker',
    'PhaseStatus',
    'ExtractorStatus',
    'PhaseProgress',
    'ExtractorProgress'
]
