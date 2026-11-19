"""SQLite adapter tests using temporary on-disk databases."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Coroutine

import httpx
import pytest

from domain.errors import LLMTimedOutError, LLMUnreachableError
from domain.schemas import (
    ExtractionMetrics,
    ExtractionTask,
    ExtractedPayload,
    TaskStatus,
)
from infrastructure.ollama_provider import OllamaLLMProvider
from infrastructure.sqlite_repo import SQLiteMetricsRepository, SQLiteTaskRepository


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Bridge async repository calls into synchronous tests."""
    return asyncio.run(coro)


def make_task(status: TaskStatus = TaskStatus.PENDING_REVIEW) -> ExtractionTask:
    return ExtractionTask(
        input_text="Sample input",
        schema={"type": "object", "required": ["summary"]},
        status=status,
        extracted_payload=ExtractedPayload(
            fields={"summary": "hello"},
            raw_llm_response='{"summary": "hello"}',
            schema_validation_success=True,
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_sqlite_task_repository_crud(tmp_path: Path) -> None:
    repo = SQLiteTaskRepository(str(tmp_path / "tasks.db"))
    saved = run(repo.add(make_task()))
    assert saved.id
    fetched = run(repo.get(saved.id or ""))
    assert fetched is not None
    assert fetched.input_text == "Sample input"
    assert fetched.extracted_payload is not None
    assert fetched.extracted_payload.fields == {"summary": "hello"}

    fetched.status = TaskStatus.APPROVED
    fetched.review_notes = "ok"
    updated = run(repo.update(fetched))
    assert updated.status is TaskStatus.APPROVED
    assert updated.review_notes == "ok"
    assert len(run(repo.list())) == 1


def test_sqlite_task_repository_status_filter(tmp_path: Path) -> None:
    repo = SQLiteTaskRepository(str(tmp_path / "tasks.db"))
    run(repo.add(make_task(TaskStatus.PENDING_REVIEW)))
    run(repo.add(make_task(TaskStatus.APPROVED)))
    assert len(run(repo.list())) == 2
    assert len(run(repo.list(TaskStatus.APPROVED))) == 1
    assert len(run(repo.list(TaskStatus.REJECTED))) == 0


def test_sqlite_export_empty_and_populated(tmp_path: Path) -> None:
    repo = SQLiteTaskRepository(str(tmp_path / "tasks.db"))
    assert run(repo.export()) == "[]"
    run(repo.add(make_task()))
    csv_text = run(repo.export(fmt="csv"))
    assert "id,status" in csv_text
    assert "pending_review" in csv_text


def test_sqlite_metrics_record_and_aggregate(tmp_path: Path) -> None:
    db_path = str(tmp_path / "tasks.db")
    tasks = SQLiteTaskRepository(db_path)
    metrics_repo = SQLiteMetricsRepository(db_path)

    empty = run(metrics_repo.aggregate())
    assert empty["total_tasks"] == 0
    assert empty["schema_validation_success_rate"] == 0.0
    assert empty["avg_latency_ms"] == 0.0

    task = run(tasks.add(make_task()))
    run(
        metrics_repo.record(
            task.id or "",
            ExtractionMetrics(
                latency_ms=20.0,
                retry_count=1,
                schema_validation_success=True,
                model_used="qwen2.5",
            ),
        )
    )
    run(tasks.add(make_task()))
    run(
        metrics_repo.record(
            "second-task",
            ExtractionMetrics(
                latency_ms=40.0,
                retry_count=3,
                schema_validation_success=False,
                model_used="gemma2",
            ),
        )
    )

    stats = run(metrics_repo.aggregate())
    assert stats["total_tasks"] == 2
    assert stats["tasks_with_metrics"] == 2
    assert stats["schema_validation_success_rate"] == 0.5
    assert stats["avg_latency_ms"] == 30.0
    assert stats["total_retries"] == 4
    assert stats["avg_retry_count"] == 2.0
    assert stats["models_used"] == ["gemma2", "qwen2.5"]
    assert stats["status_counts"]["pending_review"] == 2

    fetched = run(tasks.get(task.id or ""))
    assert fetched is not None
    assert fetched.metrics is not None
    assert fetched.metrics.latency_ms == 20.0


async def test_ollama_provider_reports_unreachable_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport failures are mapped to domain errors without real network I/O."""

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def post(self, *args: Any, **kwargs: Any) -> None:
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "infrastructure.ollama_provider.httpx.AsyncClient", FakeAsyncClient
    )
    provider = OllamaLLMProvider("http://localhost:11434", "qwen2.5")
    with pytest.raises(LLMUnreachableError):
        await provider.generate("hello")


async def test_ollama_provider_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimeoutClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "TimeoutClient":
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def post(self, *args: Any, **kwargs: Any) -> None:
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("infrastructure.ollama_provider.httpx.AsyncClient", TimeoutClient)
    provider = OllamaLLMProvider("http://localhost:11434", "qwen2.5", timeout=0.1)
    with pytest.raises(LLMTimedOutError):
        await provider.generate("hello")


def test_ollama_provider_model_property() -> None:
    provider = OllamaLLMProvider("http://localhost:11434", "gemma2")
    assert provider.model == "gemma2"
