"""Memory scoring system — recency, importance, and composite scoring."""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Strategy weights: (semantic, recency, importance)
STRATEGY_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "balanced":   (0.4, 0.3, 0.3),
    "recency":    (0.3, 0.5, 0.2),
    "importance": (0.3, 0.2, 0.5),
}

# Importance signal weights
SIGNAL_WEIGHTS: dict[str, float] = {
    "user_correction": 0.9,
    "user_preference": 0.85,
    "decision":        0.8,
    "error_correction": 0.8,
    "commitment":      0.75,
    "repeated_topic":  0.6,
    "technical_detail": 0.5,
    "general":         0.2,
}


def compute_recency_score(created_at: datetime | str, half_life_days: float = 7.0) -> float:
    """Exponential decay score. Returns 0.0–1.0."""
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    days_old = max((now - created_at).total_seconds() / 86400, 0.0)
    return math.exp(-0.693 * days_old / half_life_days)


def compute_importance_score(signals: list[str]) -> float:
    """Heuristic importance from a list of signal types. Returns 0.0–1.0."""
    if not signals:
        return SIGNAL_WEIGHTS["general"]
    scores = [SIGNAL_WEIGHTS.get(s, 0.3) for s in signals]
    return min(max(scores), 1.0)


def compute_composite_score(
    semantic_sim: float,
    recency: float,
    importance: float,
    strategy: str = "balanced",
) -> float:
    """Weighted combination of scores using the given strategy."""
    w_sem, w_rec, w_imp = STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS["balanced"])
    return w_sem * semantic_sim + w_rec * recency + w_imp * importance
