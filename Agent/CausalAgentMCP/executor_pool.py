"""Bounded CPU execution with admission control and late-result isolation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import itertools
from typing import Any, Callable, Mapping

try:
    import resource as _resource
except ImportError:  # pragma: no cover - Windows worker fallback
    _resource = None

from Agent.deep_agent_tools.error_codes import SafeErrorCode


@dataclass(frozen=True)
class _ProcessExecutionEnvelope:
    value: Any
    peak_rss_bytes: int
    cpu_seconds: float


def _run_runner(runner: Callable[..., Any], csv_data: str, parameters: Mapping[str, Any]) -> Any:
    """Top-level callable so a spawned process receives only pure data."""

    # Third-party causal libraries may print progress, warnings or file paths;
    # never let child-process output share the service protocol/log stream.
    before = _resource.getrusage(_resource.RUSAGE_SELF) if _resource else None
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        value = runner(csv_data, parameters)
    after = _resource.getrusage(_resource.RUSAGE_SELF) if _resource else None
    peak_rss_bytes = int(getattr(after, "ru_maxrss", 0) or 0) * 1024
    cpu_seconds = 0.0
    if before is not None and after is not None:
        cpu_seconds = max(
            0.0,
            (after.ru_utime + after.ru_stime)
            - (before.ru_utime + before.ru_stime),
        )
    return _ProcessExecutionEnvelope(value, peak_rss_bytes, cpu_seconds)


class PoolExecutionError(RuntimeError):
    def __init__(
        self,
        code: SafeErrorCode,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code.value)
        self.safe_error_code = code
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class ExecutionOutcome:
    value: Any
    executor_slot_id: str
    peak_rss_bytes: int = 0
    cpu_seconds: float = 0.0


class BoundedProcessPool:
    """Limit running plus queued work without pretending Future.cancel kills CPU work."""

    def __init__(
        self,
        *,
        process_workers: int = 2,
        queue_capacity: int = 4,
        enqueue_timeout_seconds: float = 5.0,
        timeout_recycle_threshold: int = 3,
        executor_factory: Callable[..., Any] | None = None,
    ) -> None:
        if process_workers <= 0 or queue_capacity < 0:
            raise ValueError("process_workers must be positive and queue_capacity non-negative")
        self.process_workers = process_workers
        self.queue_capacity = queue_capacity
        self.enqueue_timeout_seconds = enqueue_timeout_seconds
        self.timeout_recycle_threshold = timeout_recycle_threshold
        self._executor_factory = executor_factory or ProcessPoolExecutor
        self._executor: Any | None = None
        self._admission = asyncio.Semaphore(process_workers + queue_capacity)
        self._capability_limits: dict[str, asyncio.Semaphore] = {}
        self._inflight: set[asyncio.Future[Any]] = set()
        self._sequence = itertools.count()
        self._consecutive_timeouts = 0
        self._recycle_task: asyncio.Task[Any] | None = None
        self._closed = False

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("process pool is closed")
        if self._executor is None:
            self._executor = self._executor_factory(max_workers=self.process_workers)

    async def close(self) -> None:
        self._closed = True
        if self._recycle_task and not self._recycle_task.done():
            self._recycle_task.cancel()
            await asyncio.gather(self._recycle_task, return_exceptions=True)
        executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def ready(self) -> bool:
        return not self._closed and self._executor is not None

    async def execute(
        self,
        *,
        capability_id: str,
        runner: Callable[..., Any],
        csv_data: str,
        parameters: Mapping[str, Any],
        timeout_seconds: float,
        concurrency: int,
    ) -> ExecutionOutcome:
        if not self.ready():
            raise PoolExecutionError(SafeErrorCode.MCP_CAPACITY_EXHAUSTED)
        capability_semaphore = self._capability_limits.setdefault(
            capability_id, asyncio.Semaphore(concurrency)
        )
        try:
            await asyncio.wait_for(
                capability_semaphore.acquire(), self.enqueue_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise PoolExecutionError(
                SafeErrorCode.MCP_CAPACITY_EXHAUSTED, retry_after_seconds=1
            ) from exc
        try:
            try:
                await asyncio.wait_for(
                    self._admission.acquire(), self.enqueue_timeout_seconds
                )
            except asyncio.TimeoutError as exc:
                raise PoolExecutionError(
                    SafeErrorCode.MCP_CAPACITY_EXHAUSTED, retry_after_seconds=1
                ) from exc

            loop = asyncio.get_running_loop()
            executor = self._executor
            if executor is None:
                self._admission.release()
                capability_semaphore.release()
                raise PoolExecutionError(SafeErrorCode.MCP_CAPACITY_EXHAUSTED)
            try:
                future = asyncio.ensure_future(
                    loop.run_in_executor(
                        executor, _run_runner, runner, csv_data, dict(parameters)
                    )
                )
            except BaseException:
                self._admission.release()
                capability_semaphore.release()
                raise
            self._inflight.add(future)
            future.add_done_callback(
                lambda completed: self._release(completed, capability_semaphore)
            )
            try:
                value = await asyncio.wait_for(asyncio.shield(future), timeout_seconds)
            except asyncio.TimeoutError as exc:
                self._consecutive_timeouts += 1
                self._schedule_recycle_if_needed()
                raise PoolExecutionError(
                    SafeErrorCode.ALGORITHM_TIMED_OUT
                ) from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise PoolExecutionError(
                    SafeErrorCode.ALGORITHM_EXECUTION_FAILED
                ) from exc
            else:
                self._consecutive_timeouts = 0
                if isinstance(value, _ProcessExecutionEnvelope):
                    execution_value = value.value
                    peak_rss_bytes = value.peak_rss_bytes
                    cpu_seconds = value.cpu_seconds
                else:
                    execution_value = value
                    peak_rss_bytes = 0
                    cpu_seconds = 0.0
                return ExecutionOutcome(
                    value=execution_value,
                    executor_slot_id=f"process-{next(self._sequence) % self.process_workers}",
                    peak_rss_bytes=peak_rss_bytes,
                    cpu_seconds=cpu_seconds,
                )
        except BaseException:
            raise

    def _release(
        self,
        future: asyncio.Future[Any],
        capability_semaphore: asyncio.Semaphore,
    ) -> None:
        self._inflight.discard(future)
        self._admission.release()
        capability_semaphore.release()

    def _schedule_recycle_if_needed(self) -> None:
        if (
            self._consecutive_timeouts < self.timeout_recycle_threshold
            or self._recycle_task is not None
        ):
            return
        self._recycle_task = asyncio.create_task(self.recycle())

    async def recycle(self) -> None:
        """Replace the pool after repeated timeouts; late futures remain isolated."""

        old_executor = self._executor
        if self._closed:
            return
        self._executor = self._executor_factory(max_workers=self.process_workers)
        self._consecutive_timeouts = 0
        try:
            from observability.logging_runtime import log_event
            import logging

            log_event(
                logging.getLogger(__name__),
                "mcp.process.recycled",
                details={"reason_code": "timeout"},
            )
        except Exception:
            pass
        if old_executor is not None:
            old_executor.shutdown(wait=False, cancel_futures=True)
