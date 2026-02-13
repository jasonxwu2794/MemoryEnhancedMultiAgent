"""Retry utility with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable, Tuple, Type

logger = logging.getLogger(__name__)


async def retry_with_backoff(
    fn: Callable,
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    **kwargs: Any,
) -> Any:
    """Call an async function with exponential backoff + jitter on failure.

    Args:
        fn: Async callable to retry.
        max_retries: Maximum number of attempts (total, including first).
        base_delay: Base delay in seconds (doubles each retry).
        exceptions: Tuple of exception types to catch and retry on.

    Returns:
        The result of fn(*args, **kwargs) on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            return await fn(*args, **kwargs)
        except exceptions as e:
            last_exc = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Retry {attempt + 1}/{max_retries} for {fn.__name__}: {e} "
                    f"(waiting {delay:.1f}s)"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_retries} retries exhausted for {fn.__name__}: {e}")
    raise last_exc  # type: ignore[misc]
