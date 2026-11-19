"""Domain-layer errors.

All errors are plain Python exceptions with no framework dependencies. The
presentation layer maps them to HTTP status codes and structured error bodies.
"""


class DomainError(Exception):
    """Base class for all domain errors."""


class TaskNotFoundError(DomainError):
    """Raised when a requested task_id does not exist."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class InvalidStatusTransitionError(DomainError):
    """Raised when a status transition is not allowed by the lifecycle."""

    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid status transition from '{current}' to '{target}'."
        )


class EmptyInputError(DomainError):
    """Raised when the input text is empty or whitespace-only."""

    def __init__(self):
        super().__init__("Input text is empty or whitespace-only.")


class InputTooLongError(DomainError):
    """Raised when input text exceeds the configured maximum length."""

    def __init__(self, length: int, maximum: int):
        self.length = length
        self.maximum = maximum
        super().__init__(
            f"Input text is too long: {length} characters (maximum {maximum})."
        )


class ExtractionError(DomainError):
    """Base class for errors raised during LLM extraction/parsing."""


class ValidationFailedError(ExtractionError):
    """Raised when extraction cannot be repaired into a schema-valid payload."""


class LLMProviderError(DomainError):
    """Base class for LLM provider errors."""


class LLMUnreachableError(LLMProviderError):
    """Raised when the LLM backend cannot be reached."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        super().__init__(f"LLM provider unreachable at {base_url}")


class LLMTimedOutError(LLMProviderError):
    """Raised when the LLM provider exceeds the configured timeout."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        super().__init__(f"LLM provider timed out after {timeout}s")


class SchemaError(DomainError):
    """Raised for an invalid or unsupported extraction schema."""


class ConfigurationError(DomainError):
    """Raised when application configuration is invalid or missing."""
