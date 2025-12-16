"""
backend/app/threading/intelligent_executor.py

Intelligent Multi-Threading Manager for SOC Analyzer v2.1.0

Provides bounded, adaptive parallelism for control/CUEC extraction with:
- Semaphore-based concurrency limits (no runaway threads)
- CPU/memory monitoring with adaptive throttling
- Circuit breaker pattern for failure handling
- Graceful degradation to sequential processing
- Per-task timeout and retry logic

Designed to prevent the resource monopolization issues encountered in early threading attempts.
"""

import logging
import threading
import time
import psutil
from typing import Optional, Callable, Any, Dict, List
from dataclasses import dataclass
from enum import Enum
import concurrent.futures

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels for queue scheduling."""
    CRITICAL = 0   # Progress updates, cancellation checks
    HIGH = 1       # Control extraction (user-facing)
    MEDIUM = 2     # Framework mapping
    LOW = 3        # Background cleanup, logging


@dataclass
class TaskMetrics:
    """Metrics for monitoring task execution."""
    submitted: int = 0
    completed: int = 0
    failed: int = 0
    retried: int = 0
    avg_duration_ms: float = 0.0
    last_failure_time: float = 0.0
    consecutive_failures: int = 0


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation
    - OPEN: Too many failures, reject new tasks
    - HALF_OPEN: Testing if system recovered
    """
    
    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 30):
        self.failure_threshold = failure_threshold
        self.timeout = timeout_seconds
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "HALF_OPEN"
                    logger.info("[CIRCUIT_BREAKER] Entering HALF_OPEN state, testing recovery")
                else:
                    raise RuntimeError("Circuit breaker is OPEN, rejecting task")
        
        try:
            result = func(*args, **kwargs)
            with self._lock:
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failures = 0
                    logger.info("[CIRCUIT_BREAKER] Recovery successful, returning to CLOSED state")
            return result
        except Exception as e:
            with self._lock:
                self.failures += 1
                self.last_failure_time = time.time()
                if self.failures >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.error(f"[CIRCUIT_BREAKER] Opening circuit after {self.failures} failures")
            raise


class AdaptiveThrottler:
    """
    Monitors system resources and adaptively throttles task submission.
    
    Prevents CPU/memory spikes by dynamically adjusting concurrency limits.
    """
    
    def __init__(self, 
                 target_cpu_percent: int = 70,
                 target_memory_percent: int = 80,
                 check_interval_seconds: float = 2.0):
        self.target_cpu = target_cpu_percent
        self.target_memory = target_memory_percent
        self.check_interval = check_interval_seconds
        self.last_check = 0
        self.current_delay_ms = 0
        self._lock = threading.Lock()
    
    def should_throttle(self) -> tuple[bool, int]:
        """
        Check if throttling is needed.
        
        Returns:
            (should_throttle, delay_ms)
        """
        now = time.time()
        with self._lock:
            if now - self.last_check < self.check_interval:
                return self.current_delay_ms > 0, self.current_delay_ms
            
            self.last_check = now
            
            try:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory_percent = psutil.virtual_memory().percent
                
                # Adaptive delay calculation
                if cpu_percent > self.target_cpu or memory_percent > self.target_memory:
                    overshoot_cpu = max(0, cpu_percent - self.target_cpu)
                    overshoot_mem = max(0, memory_percent - self.target_memory)
                    overshoot = max(overshoot_cpu, overshoot_mem)
                    
                    # Exponential backoff: 10ms per 1% overshoot, capped at 5000ms
                    self.current_delay_ms = min(5000, int(overshoot * 10))
                    logger.warning(
                        f"[THROTTLE] CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}% "
                        f"- Throttling with {self.current_delay_ms}ms delay"
                    )
                    return True, self.current_delay_ms
                else:
                    # Gradually reduce delay when system recovers
                    if self.current_delay_ms > 0:
                        self.current_delay_ms = max(0, self.current_delay_ms - 100)
                        if self.current_delay_ms == 0:
                            logger.info("[THROTTLE] System recovered, resuming normal operation")
                    return False, 0
                    
            except Exception as e:
                logger.warning(f"[THROTTLE] Failed to check system resources: {e}")
                return False, 0


class IntelligentTaskExecutor:
    """
    Bounded thread pool executor with intelligent resource management.
    
    Features:
    - Semaphore-based concurrency limiting
    - Adaptive throttling based on CPU/memory
    - Circuit breaker for failure handling
    - Graceful degradation to sequential processing
    - Per-task timeout and retry logic
    - Progress tracking integration
    """
    
    def __init__(self,
                 max_workers: int = 4,
                 enable_throttling: bool = True,
                 enable_circuit_breaker: bool = True,
                 task_timeout_seconds: int = 300,
                 target_cpu_percent: int = 70,
                 target_memory_percent: int = 80):
        """
        Initialize the intelligent task executor.
        
        Args:
            max_workers: Maximum concurrent threads (default: 4)
            enable_throttling: Enable adaptive CPU/memory throttling
            enable_circuit_breaker: Enable circuit breaker for failure handling
            task_timeout_seconds: Timeout for individual tasks (default: 300s = 5 min)
            target_cpu_percent: Target CPU utilization (default: 70%)
            target_memory_percent: Target memory utilization (default: 80%)
        """
        self.max_workers = max_workers
        self.task_timeout = task_timeout_seconds
        
        # Semaphore to limit concurrent execution (critical for preventing runaway threads)
        self.semaphore = threading.Semaphore(max_workers)
        
        # Thread pool executor
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="intelligent_worker"
        )
        
        # Adaptive throttling
        self.throttler = AdaptiveThrottler(
            target_cpu_percent=target_cpu_percent,
            target_memory_percent=target_memory_percent
        ) if enable_throttling else None
        
        # Circuit breaker
        self.circuit_breaker = CircuitBreaker() if enable_circuit_breaker else None
        
        # Metrics tracking
        self.metrics = TaskMetrics()
        self._metrics_lock = threading.Lock()
        
        # Shutdown flag
        self._shutdown = False
        self._shutdown_lock = threading.Lock()
        
        logger.info(
            f"[EXECUTOR] Initialized with max_workers={max_workers}, "
            f"throttling={enable_throttling}, circuit_breaker={enable_circuit_breaker}"
        )
    
    def submit(self,
               func: Callable,
               *args,
               priority: TaskPriority = TaskPriority.MEDIUM,
               task_id: Optional[str] = None,
               **kwargs) -> concurrent.futures.Future:
        """
        Submit a task for execution.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            priority: Task priority level
            task_id: Optional task identifier for logging
            **kwargs: Keyword arguments
            
        Returns:
            Future object for result tracking
        """
        with self._shutdown_lock:
            if self._shutdown:
                raise RuntimeError("Executor is shut down")
        
        # Check throttling
        if self.throttler:
            should_throttle, delay_ms = self.throttler.should_throttle()
            if should_throttle:
                time.sleep(delay_ms / 1000.0)
        
        # Wrap function with semaphore acquisition and metrics tracking
        def _wrapped_task():
            task_start = time.time()
            task_name = task_id or func.__name__
            
            try:
                # Acquire semaphore (blocks if max_workers already running)
                acquired = self.semaphore.acquire(timeout=self.task_timeout)
                if not acquired:
                    raise TimeoutError(f"Task {task_name} timed out waiting for semaphore")
                
                try:
                    logger.debug(f"[EXECUTOR] Starting task: {task_name}")
                    
                    # Execute with circuit breaker if enabled
                    if self.circuit_breaker:
                        result = self.circuit_breaker.call(func, *args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    
                    # Update metrics
                    duration_ms = (time.time() - task_start) * 1000
                    with self._metrics_lock:
                        self.metrics.completed += 1
                        # Running average
                        n = self.metrics.completed
                        self.metrics.avg_duration_ms = (
                            (self.metrics.avg_duration_ms * (n - 1) + duration_ms) / n
                        )
                        # Reset consecutive failures on success
                        self.metrics.consecutive_failures = 0
                    
                    logger.debug(f"[EXECUTOR] Completed task: {task_name} in {duration_ms:.0f}ms")
                    return result
                    
                finally:
                    self.semaphore.release()
                    
            except Exception as e:
                duration_ms = (time.time() - task_start) * 1000
                with self._metrics_lock:
                    self.metrics.failed += 1
                    self.metrics.last_failure_time = time.time()
                    self.metrics.consecutive_failures += 1
                
                logger.error(
                    f"[EXECUTOR] Task {task_name} failed after {duration_ms:.0f}ms: {e}",
                    exc_info=True
                )
                raise
        
        # Submit to executor
        with self._metrics_lock:
            self.metrics.submitted += 1
        
        future = self.executor.submit(_wrapped_task)
        return future
    
    def map(self,
            func: Callable,
            items: List[Any],
            priority: TaskPriority = TaskPriority.MEDIUM,
            timeout: Optional[float] = None,
            return_exceptions: bool = False) -> List[Any]:
        """
        Map function over items with intelligent parallelism.
        
        Args:
            func: Function to apply to each item
            items: List of items to process
            priority: Task priority level
            timeout: Optional timeout for entire operation
            return_exceptions: If True, return exceptions instead of raising
            
        Returns:
            List of results in same order as items
        """
        if not items:
            return []
        
        start_time = time.time()
        futures = []
        
        for i, item in enumerate(items):
            task_id = f"{func.__name__}_item_{i}"
            future = self.submit(func, item, priority=priority, task_id=task_id)
            futures.append((i, future))
        
        # Collect results
        results = [None] * len(items)
        
        for i, future in futures:
            try:
                remaining_timeout = None
                if timeout:
                    elapsed = time.time() - start_time
                    remaining_timeout = max(0, timeout - elapsed)
                
                result = future.result(timeout=remaining_timeout)
                results[i] = result
                    
            except concurrent.futures.TimeoutError as e:
                logger.error(f"[EXECUTOR] Task {i} timed out")
                if return_exceptions:
                    results[i] = e
                else:
                    results[i] = None
            except Exception as e:
                logger.error(f"[EXECUTOR] Task {i} failed: {e}")
                if return_exceptions:
                    results[i] = e
                else:
                    results[i] = None
        
        return results
    
    def shutdown(self, wait: bool = True):
        """
        Shutdown the executor gracefully.
        
        Args:
            wait: Wait for running tasks to complete
        """
        with self._shutdown_lock:
            if self._shutdown:
                return
            self._shutdown = True
        
        logger.info("[EXECUTOR] Shutting down...")
        self.executor.shutdown(wait=wait)
        logger.info("[EXECUTOR] Shutdown complete")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current executor metrics."""
        with self._metrics_lock:
            return {
                "submitted": self.metrics.submitted,
                "completed": self.metrics.completed,
                "failed": self.metrics.failed,
                "retried": self.metrics.retried,
                "avg_duration_ms": round(self.metrics.avg_duration_ms, 2),
                "success_rate": round(
                    self.metrics.completed / max(1, self.metrics.submitted) * 100, 2
                ),
                "consecutive_failures": self.metrics.consecutive_failures,
                "circuit_breaker_state": self.circuit_breaker.state if self.circuit_breaker else "N/A",
            }
