"""Abstract ports (interfaces) defined by the domain layer.

Implementations live exclusively in ``infrastructure/``. Neither this module
nor anything in ``domain/`` or ``application/`` imports FastAPI, SQLAlchemy,
httpx, or Ollama. Swapping Ollama for another LLM or SQLite for another store
only requires new implementations of these ports plus DI wiring changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

ParsedOutput = tuple[dict[str, Any] | None, bool, str, int]

from domain.schemas import ExtractionMetrics, ExtractionTask, TaskStatus


@runtime_checkable
class LLMProvider(Protocol):
    """Port for generating text from a local (or remote) LLM."""

    @property
    def model(self) -> str:  # pragma: no cover - interface documentation
        """Identifier of the model backing this provider."""

    async def generate(self, prompt: str, system: str | None = None) -> str:  # pragma: no cover
        """Generate a completion for ``prompt``.

        Returns the raw model output string. Implementations must raise
        :class:`domain.errors.LLMUnreachableError` or
        :class:`domain.errors.LLMTimedOutError` on transport failures so the
        application layer can handle them uniformly.
        """


@runtime_checkable
class StructuredOutputParser(Protocol):
    """Port for parsing/validating raw LLM output into structured fields.

    Implementations live in infrastructure and may perform bounded repair
    retries. The application layer only sees this interface.
    """

    def parse(  # pragma: no cover - interface documentation
        self, raw_response: str, schema: dict[str, Any], *, max_retries: int = 2
    ) -> ParsedOutput:
        """Return ``(payload, success, diagnostic, retry_count)``."""


class TaskRepository(ABC):
    """Port for persisting and querying extraction tasks."""

    @abstractmethod
    async def add(self, task: ExtractionTask) -> ExtractionTask:  # pragma: no cover
        """Persist a new task and return it with its assigned id/timestamps."""

    @abstractmethod
    async def get(self, task_id: str) -> ExtractionTask | None:  # pragma: no cover
        """Return a task by id, or ``None`` when it does not exist."""

    @abstractmethod
    async def list(self, status: TaskStatus | None = None) -> list[ExtractionTask]:  # pragma: no cover
        """Return all tasks, optionally filtered by status."""

    @abstractmethod
    async def update(self, task: ExtractionTask) -> ExtractionTask:  # pragma: no cover
        """Persist changes to an existing task (review edits, status, notes)."""

    @abstractmethod
    async def export(  # pragma: no cover
        self, status: TaskStatus | None = None, fmt: str = "json"
    ) -> str:
        """Export filtered tasks as JSON or CSV text."""


class MetricsRepository(ABC):
    """Port for recording and aggregating observability metrics."""

    @abstractmethod
    async def record(self, task_id: str, metrics: ExtractionMetrics) -> None:  # pragma: no cover
        """Record per-task metrics."""

    @abstractmethod
    async def aggregate(self) -> dict[str, Any]:  # pragma: no cover
        """Return aggregated observability statistics (empty-state safe)."""
