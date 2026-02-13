"""Custom exception classes for the MemoryEnhancedMultiAgent system."""


class AgentError(Exception):
    """Base exception for all agent errors."""
    def __init__(self, message: str, recovery_hint: str = ""):
        self.recovery_hint = recovery_hint
        super().__init__(message)


class LLMError(AgentError):
    """API/LLM communication issues."""
    def __init__(self, message: str, provider: str = "", status_code: int = 0, recovery_hint: str = ""):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message, recovery_hint or "Check API key and provider status")


class MemoryDBError(AgentError):
    """Database/memory issues."""
    def __init__(self, message: str, recovery_hint: str = ""):
        super().__init__(message, recovery_hint or "Memory will continue without persistence")


class DelegationError(AgentError):
    """Session/delegation issues."""
    def __init__(self, message: str, agent_name: str = "", recovery_hint: str = ""):
        self.agent_name = agent_name
        super().__init__(message, recovery_hint or "Brain will handle the task directly")


class ConfigError(AgentError):
    """Missing configuration or API keys."""
    def __init__(self, message: str, recovery_hint: str = ""):
        super().__init__(message, recovery_hint or "Check environment variables and config files")
