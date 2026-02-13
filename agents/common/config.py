"""Centralized configuration for the multi-agent system."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Central config — replaces hardcoded paths scattered across modules."""

    memory_db_path: str = "data/memory.db"
    messages_db_path: str = "data/messages.db"
    projects_db_path: str = "data/projects.db"
    usage_db_path: str = "data/usage.db"
    activity_db_path: str = "data/activity.db"
    workspace_path: str = "."
    verbose_mode: bool = False
    memory_tier: str = "full"
    embedding_type: str = "local"

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load config from environment variables with sensible defaults."""
        return cls(
            memory_db_path=os.environ.get("MEMORY_DB_PATH", "data/memory.db"),
            messages_db_path=os.environ.get("MESSAGES_DB_PATH", "data/messages.db"),
            projects_db_path=os.environ.get("PROJECTS_DB_PATH", "data/projects.db"),
            usage_db_path=os.environ.get("USAGE_DB_PATH", "data/usage.db"),
            activity_db_path=os.environ.get("ACTIVITY_DB_PATH", "data/activity.db"),
            workspace_path=os.environ.get("WORKSPACE_PATH", "."),
            verbose_mode=os.environ.get("VERBOSE_MODE", "").lower() in ("1", "true", "yes"),
            memory_tier=os.environ.get("MEMORY_TIER", "full"),
            embedding_type=os.environ.get("EMBEDDING_TYPE", "local"),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "AgentConfig":
        """Load from a YAML config file. Falls back to defaults for missing keys."""
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()
