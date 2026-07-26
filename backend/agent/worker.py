from __future__ import annotations

import asyncio
import multiprocessing
import queue
import threading
import uuid
from dataclasses import dataclass
from typing import Any


def _process_entry(tool_name: str, arguments: dict[str, Any], output) -> None:
    try:
        from agent.tools.registry import invoke_tool_sync

        result = invoke_tool_sync(tool_name, arguments)
        output.put(("ok", result))
    except BaseException as exc:
        output.put(("error", f"{type(exc).__name__}: {exc}"))


@dataclass
class WorkerTask:
    task_id: str
    execution_id: str
    process: multiprocessing.Process


class HeavyWorkerManager:
    """Runs a blocking tool in a dedicated process that can be terminated."""

    def __init__(self) -> None:
        self._context = multiprocessing.get_context("spawn")
        self._active: dict[str, WorkerTask] = {}
        self._lock = threading.Lock()

    async def run(
        self,
        *,
        execution_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
        cancel_event: asyncio.Event | None = None,
    ) -> Any:
        task_id = uuid.uuid4().hex
        output = self._context.Queue(maxsize=1)
        process = self._context.Process(
            target=_process_entry,
            args=(tool_name, arguments, output),
            daemon=False,
            name=f"qidian-tool-{tool_name}-{task_id[:8]}",
        )
        record = WorkerTask(task_id, execution_id, process)
        with self._lock:
            self._active[task_id] = record
        process.start()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise asyncio.CancelledError
                try:
                    status, payload = output.get_nowait()
                except queue.Empty:
                    status = ""
                    payload = None
                if status == "ok":
                    return payload
                if status == "error":
                    raise RuntimeError(str(payload))
                if not process.is_alive():
                    raise RuntimeError(
                        f"heavy worker exited without a result (exit={process.exitcode})"
                    )
                if loop.time() >= deadline:
                    raise TimeoutError(f"tool {tool_name} exceeded {timeout_seconds}s")
                await asyncio.sleep(0.05)
        finally:
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 2)
                if process.is_alive() and hasattr(process, "kill"):
                    process.kill()
            else:
                await asyncio.to_thread(process.join, 1)
            output.close()
            with self._lock:
                self._active.pop(task_id, None)

    async def cancel_execution(self, execution_id: str) -> None:
        with self._lock:
            processes = [
                task.process
                for task in self._active.values()
                if task.execution_id == execution_id
            ]
        for process in processes:
            if process.is_alive():
                process.terminate()


heavy_worker_manager = HeavyWorkerManager()
