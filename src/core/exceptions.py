"""
Shared Exceptions for Pipeline Tools
=====================================
Standardized exception hierarchy for LLM routing, quota management,
authentication validation, and batch execution lifecycle.
"""

class LLMError(Exception):
    """Base exception for LLM service operations."""
    pass


class LLMQuotaExceededError(LLMError):
    """Raised when provider quota is exhausted or rate limit is hit (e.g. 429 RESOURCE_EXHAUSTED)."""
    pass


class LLMAuthError(LLMError):
    """Raised when API key or credentials are invalid (e.g. 401/403/API_KEY_INVALID)."""
    pass


class LLMServiceUnavailableError(LLMError):
    """Raised when local or remote LLM service cannot be reached or server is unavailable."""
    pass


class LLMExecutionCancelledError(LLMError):
    """Raised when a batch execution is cancelled by the user."""
    pass
