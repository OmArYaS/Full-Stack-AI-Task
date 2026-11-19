"""Shared offline test fixtures and in-memory fakes.

No Ollama server, network service, or paid API is used in any test. The LLM
provider and repositories are replaced with deterministic fakes through
FastAPI dependency overrides.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Make the backend/app package root importable when running pytest from repo root.
_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_APP = _ROOT / "backend" / "app"
if str(_BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(_BACKEND_APP))

from domain.errors import DomainError  # noqa: E402
from domain.ports import MetricsRepository, TaskRepository  # noqa: E402
from domain.schemas import (  # noqa: E402
    ExtractionMetrics,
    ExtractionTask,
    TaskStatus,
)
from infrastructure.config import Settings  # noqa: E402
from presentation.deps import (  # noqa: E402
    get_llm_provider,
    get_metrics_repository,
    get_task_repository,
)
from presentation.main import create_app  # noqa: E402


DEFAULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "entities": {"type": "array", "items": {"type": "string"}},
        "sentiment": {
            "type": "string",
            "enum": ["positive", "negative", "neutral"],
        },
    },
    "required": ["summary"],
}


VALID_JSON = '{"summary": "A short summary", "entities": ["Ada"], "sentiment": "positive"}'


class FakeLLMProvider:
    """Deterministic LLM provider fake implementing the domain port."""

    def __init__(
        self,
        responses: str | list[str] = VALID_JSON,
        *,
        model: str = "fake-model",
        error: Exception | None = None,
    ) -> None:
        self._responses = list(responses) if isinstance(responses, list) else [responses]
        self.model = model
        self.error = error
        self.prompts: list[str] = []

    def set_response(self, response: str | list[str]) -> None:
        """Replace queued responses."""
        self._responses = list(response) if isinstance(response, list) else [response]
        self.error = None

    def set_error(self, error: Exception) -> None:
        """Make the next generate() call raise ``error``."""
        self.error = error

    async def generate(self, prompt: str, system: str | None = None) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        if not self._responses:
            return VALID_JSON
        return self._responses.pop(0)


class InMemoryTaskRepository(TaskRepository):
    """Task repository fake backed by a dict."""

    def __init__(self) -> None:
        self._store: dict[str, ExtractionTask] = {}

    async def add(self, task: ExtractionTask) -> ExtractionTask:
        from datetime import datetime, timezone
        from uuid import uuid4

        saved = deepcopy(task)
        saved.id = saved.id or str(uuid4())
        saved.created_at = saved.created_at or datetime.now(timezone.utc)
        saved.updated_at = saved.updated_at or saved.created_at
        self._store[saved.id] = deepcopy(saved)
        return deepcopy(saved)

    async def get(self, task_id: str) -> ExtractionTask | None:
        task = self._store.get(task_id)
        return deepcopy(task) if task else None

    async def list(self, status: TaskStatus | None = None) -> list[ExtractionTask]:
        tasks = [
            task
            for task in self._store.values()
            if status is None or task.status == status
        ]
        return sorted(tasks, key=lambda t: t.created_at or t.id)

    async def update(self, task: ExtractionTask) -> ExtractionTask:
        if task.id not in self._store:
            raise DomainError(f"Task not found: {task.id}")
        self._store[task.id] = deepcopy(task)
        return deepcopy(task)

    async def export(self, status: TaskStatus | None = None, fmt: str = "json") -> str:
        import json

        tasks = await self.list(status)
        if fmt == "csv":
            return "id,status\n" + "".join(f"{t.id},{t.status.value}\n" for t in tasks)
        return json.dumps([t.model_dump(mode="json") for t in tasks])


class InMemoryMetricsRepository(MetricsRepository):
    """Metrics repository fake with empty-state-safe aggregation."""

    def __init__(self, task_repository: TaskRepository | None = None) -> None:
        self._records: dict[str, ExtractionMetrics] = {}
        self.task_repository = task_repository

    async def record(self, task_id: str, metrics: ExtractionMetrics) -> None:
        self._records[task_id] = metrics.model_copy(deep=True)

    async def aggregate(self) -> dict[str, Any]:
        values = list(self._records.values())
        n = len(values)
        success = sum(1 for m in values if m.schema_validation_success)
        status_counts = {status.value: 0 for status in TaskStatus}
        if self.task_repository is not None:
            for task in await self.task_repository.list():
                status_counts[task.status.value] += 1
        return {
            "total_tasks": n,
            "status_counts": status_counts,
            "tasks_with_metrics": n,
            "schema_validation_success_count": success,
            "schema_validation_success_rate": (success / n) if n else 0.0,
            "avg_latency_ms": (sum(m.latency_ms for m in values) / n) if n else 0.0,
            "total_retries": sum(m.retry_count for m in values),
            "avg_retry_count": (sum(m.retry_count for m in values) / n) if n else 0.0,
            "models_used": sorted({m.model_used for m in values}),
        }


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def schema() -> dict[str, Any]:
    return deepcopy(DEFAULT_SCHEMA)


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def task_repo() -> InMemoryTaskRepository:
    return InMemoryTaskRepository()


@pytest.fixture
def metrics_repo() -> InMemoryMetricsRepository:
    return InMemoryMetricsRepository()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        MAX_INPUT_LENGTH=500,
        DEFAULT_MAX_RETRIES=2,
        DEFAULT_SCHEMA=deepcopy(DEFAULT_SCHEMA),
        DB_PATH=str(tmp_path / "test.db"),
    )


@pytest.fixture
def client(
    fake_llm: FakeLLMProvider,
    task_repo: InMemoryTaskRepository,
    metrics_repo: InMemoryMetricsRepository,
    settings: Settings,
) -> TestClient:
    """FastAPI client with all ports overridden by deterministic fakes."""
    metrics_repo.task_repository = task_repo
    app = create_app(settings)
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[get_task_repository] = lambda: task_repo
    app.dependency_overrides[get_metrics_repository] = lambda: metrics_repo
    with TestClient(app) as test_client:
        yield test_client
