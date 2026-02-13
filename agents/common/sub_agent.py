"""Sub-agent pool for parallel LLM work within a parent agent's process."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from agents.common.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class SubTask:
    """A lightweight task for a sub-agent LLM call."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubResult:
    """Result from a sub-agent LLM call."""
    task_id: str = ""
    success: bool = False
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    tokens_used: int = 0
    confidence: float = 0.0


class SubAgentPool:
    """Pool for running parallel sub-agent LLM calls.

    These are lightweight concurrent LLM calls within the parent agent's
    process — NOT separate containers or sessions.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        system_prompt: str = "",
        default_model: str | None = None,
        max_concurrency: int = 5,
        task_timeout: float = 60.0,
    ):
        self.llm = llm or LLMClient()
        self.system_prompt = system_prompt
        self.default_model = default_model
        self.max_concurrency = max_concurrency
        self.task_timeout = task_timeout

        # Metrics
        self._total_tasks = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_tokens = 0
        self._total_duration_ms = 0.0

    async def execute_parallel(
        self,
        tasks: list[SubTask],
        model: str | None = None,
    ) -> list[SubResult]:
        """Run multiple sub-agent LLM calls concurrently.

        Respects max_concurrency via a semaphore.
        Returns results in the same order as tasks.
        """
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _run_with_sem(task: SubTask) -> SubResult:
            async with sem:
                return await self.execute_single(task, model=model)

        results = await asyncio.gather(
            *[_run_with_sem(t) for t in tasks],
            return_exceptions=True,
        )

        # Convert exceptions to SubResults — partial results on failure
        final: list[SubResult] = []
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.warning(f"Sub-task {task.id} failed in pool: {result}")
                final.append(SubResult(
                    task_id=task.id,
                    success=False,
                    error=str(result),
                ))
                self._total_failures += 1
            else:
                final.append(result)

        return final

    async def execute_single(
        self,
        task: SubTask,
        model: str | None = None,
    ) -> SubResult:
        """Run a single sub-agent LLM call."""
        self._total_tasks += 1
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(self.llm.generate(
                system=self.system_prompt,
                prompt=task.description,
                model=model or self.default_model,
                temperature=0.3,
            ), timeout=self.task_timeout)

            # Handle LLM error dicts
            if result.get("error"):
                duration_ms = (time.monotonic() - start) * 1000
                self._total_failures += 1
                return SubResult(
                    task_id=task.id,
                    success=False,
                    error=result.get("message", "LLM error"),
                    duration_ms=duration_ms,
                )

            duration_ms = (time.monotonic() - start) * 1000
            tokens = result.get("usage", {}).get("total_tokens", 0)

            self._total_successes += 1
            self._total_tokens += tokens
            self._total_duration_ms += duration_ms

            return SubResult(
                task_id=task.id,
                success=True,
                output=result["content"],
                duration_ms=duration_ms,
                tokens_used=tokens,
                confidence=0.7,  # default; caller can override from parsed output
            )

        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            self._total_failures += 1
            self._total_duration_ms += duration_ms

            logger.warning(f"Sub-agent task {task.id} failed: {e}")
            return SubResult(
                task_id=task.id,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

    def get_metrics(self) -> dict:
        """Return pool metrics."""
        return {
            "total_tasks": self._total_tasks,
            "successes": self._total_successes,
            "failures": self._total_failures,
            "total_tokens": self._total_tokens,
            "avg_duration_ms": (
                self._total_duration_ms / max(self._total_tasks, 1)
            ),
        }
