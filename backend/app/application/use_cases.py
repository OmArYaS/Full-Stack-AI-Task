"""Application use cases.

Orchestrate extraction tasks, human-in-the-loop review, listing/export, and
metrics aggregation using only domain schemas and ports. No framework or
vendor code is imported here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from domain.errors import (
    EmptyInputError,
    InputTooLongError,
    InvalidStatusTransitionError,
    TaskNotFoundError,
)
from domain.ports import (
    LLMProvider,
    MetricsRepository,
    StructuredOutputParser,
    TaskRepository,
)
from domain.schemas import (
    ExtractionMetrics,
    ExtractionTask,
    ExtractedPayload,
    ReviewAction,
    ReviewDecision,
    TaskStatus,
)


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Commands / results
# --------------------------------------------------------------------------- #


@dataclass(kw_only=True)
class CreateTaskCommand:
    """Input for creating and running a structured extraction task."""

    input_text: str
    schema: dict[str, Any] | None = None
    max_retries: int | None = None


@dataclass(kw_only=True)
class TaskFilters:
    status: TaskStatus | None = None


# --------------------------------------------------------------------------- #
# Use cases
# --------------------------------------------------------------------------- #


class CreateExtractionTaskUseCase:
    """Create a task, run extraction through the LLM, and persist the result.

    Depends only on domain ports — the concrete LLM provider and repository are
    injected, so this use case is model- and store-agnostic.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        task_repository: TaskRepository,
        metrics_repository: MetricsRepository,
        output_parser: StructuredOutputParser,
        *,
        max_input_length: int,
        default_schema: dict[str, Any],
        default_max_retries: int = 2,
    ) -> None:
        self._llm = llm_provider
        self._tasks = task_repository
        self._metrics = metrics_repository
        self._parser = output_parser
        self._max_input_length = max_input_length
        self._default_schema = default_schema
        self._default_max_retries = default_max_retries

    def _build_prompt(self, input_text: str, schema: dict[str, Any]) -> str:
        """Build a model-agnostic extraction prompt (no family-specific hints)."""
        schema_hint = (
            "Return exactly one JSON object matching this JSON Schema "
            "(no markdown fences, no extra prose):\n"
            f"{schema}\n\n"
        )
        return (
            "You are a careful information-extraction assistant. "
            "Extract structured information from the input text below.\n\n"
            f"{schema_hint}"
            "Input text:\n"
            f"{input_text}\n\n"
            "Rules:\n"
            "1. Output valid JSON only, matching the schema above.\n"
            "2. If a field cannot be determined from the text, omit it or use null.\n"
            "3. Do not include markdown code fences or reasoning tags.\n"
        )

    async def execute(self, command: CreateTaskCommand) -> ExtractionTask:
        """Run the full create-and-extract flow."""
        text = (command.input_text or "").strip()
        if not text:
            raise EmptyInputError()
        if len(text) > self._max_input_length:
            raise InputTooLongError(len(text), self._max_input_length)

        schema = command.schema or self._default_schema
        max_retries = (
            command.max_retries
            if command.max_retries is not None
            else self._default_max_retries
        )

        prompt = self._build_prompt(text, schema)

        # --- LLM call with clean error handling --------------------------- #
        start = perf_counter()
        try:
            raw_response = await self._llm.generate(prompt)
        except Exception:
            latency_ms = (perf_counter() - start) * 1000
            error_metrics = ExtractionMetrics(
                latency_ms=latency_ms,
                retry_count=0,
                schema_validation_success=False,
                model_used=getattr(self._llm, "model", "unknown"),
            )
            task = ExtractionTask(
                input_text=text,
                schema=schema,
                status=TaskStatus.FAILED_VALIDATION,
                error_diagnostic="LLM provider call failed.",
                metrics=error_metrics,
            )
            saved = await self._tasks.add(task)
            await self._metrics.record(saved.id or "", error_metrics)
            raise
        latency_ms = (perf_counter() - start) * 1000

        # --- Structured JSON extraction with bounded repair retries ------- #
        payload, validation_success, diagnostic, retry_count = self._parser.parse(
            raw_response, schema, max_retries=max_retries
        )

        if validation_success:
            status = TaskStatus.PENDING_REVIEW
        elif payload:
            # Parsed something, but it did not conform to the schema: a human
            # can fix the fields manually.
            status = TaskStatus.NEEDS_MANUAL_FIX
        else:
            status = TaskStatus.FAILED_VALIDATION

        metrics = ExtractionMetrics(
            latency_ms=round(latency_ms, 2),
            retry_count=retry_count,
            schema_validation_success=validation_success,
            model_used=getattr(self._llm, "model", "unknown"),
        )
        task = ExtractionTask(
            input_text=text,
            schema=schema,
            status=status,
            extracted_payload=ExtractedPayload(
                fields=payload or {},
                raw_llm_response=raw_response,
                schema_validation_success=validation_success,
            ),
            created_at=utc_now(),
            updated_at=utc_now(),
            metrics=metrics,
            error_diagnostic=diagnostic if not validation_success else None,
        )

        saved = await self._tasks.add(task)
        # Record the metrics object directly: some repositories return tasks
        # without the metrics column (metrics live in their own store/table).
        await self._metrics.record(saved.id or "", metrics)
        # Ensure the response always carries metrics, even when the repository
        # stores them in a separate location and strips them on write.
        saved.metrics = metrics
        return saved


class GetTaskUseCase:
    """Fetch a single task by id, raising a domain error when missing."""

    def __init__(self, task_repository: TaskRepository) -> None:
        self._tasks = task_repository

    async def execute(self, task_id: str) -> ExtractionTask:
        task = await self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task


class ListTasksUseCase:
    """List tasks, optionally filtered by status."""

    def __init__(self, task_repository: TaskRepository) -> None:
        self._tasks = task_repository

    async def execute(self, filters: TaskFilters) -> list[ExtractionTask]:
        return await self._tasks.list(filters.status)


class ReviewTaskUseCase:
    """Human-in-the-loop review: edit fields, approve, or reject a task."""

    # Allowed status transitions for a review decision.
    _TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
        TaskStatus.PENDING_REVIEW: {
            TaskStatus.APPROVED,
            TaskStatus.REJECTED,
        },
        TaskStatus.NEEDS_MANUAL_FIX: {
            TaskStatus.PENDING_REVIEW,
            TaskStatus.APPROVED,
            TaskStatus.REJECTED,
        },
        TaskStatus.FAILED_VALIDATION: {
            TaskStatus.APPROVED,
            TaskStatus.REJECTED,
        },
        TaskStatus.APPROVED: frozenset(),
        TaskStatus.REJECTED: frozenset(),
    }

    def __init__(self, task_repository: TaskRepository) -> None:
        self._tasks = task_repository

    async def execute(
        self, task_id: str, action: ReviewAction
    ) -> ExtractionTask:
        task = await self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        target_status = (
            TaskStatus.APPROVED if action.decision == ReviewDecision.APPROVED else TaskStatus.REJECTED
        )
        allowed = self._TRANSITIONS.get(task.status, frozenset())
        if target_status not in allowed:
            raise InvalidStatusTransitionError(
                task.status.value, target_status.value
            )

        # Apply manual field edits when provided.
        if action.fields is not None:
            if task.extracted_payload is None:
                task.extracted_payload = ExtractedPayload(fields={})
            merged: dict[str, Any] = dict(task.extracted_payload.fields)
            merged.update(action.fields)
            task.extracted_payload.fields = merged
            task.extracted_payload.schema_validation_success = False  # re-validate on next run

        task.status = target_status
        task.review_notes = action.notes
        task.reviewed_by = action.reviewer
        task.updated_at = utc_now()

        return await self._tasks.update(task)


class ExportTasksUseCase:
    """Export filtered tasks as JSON or CSV text."""

    def __init__(self, task_repository: TaskRepository) -> None:
        self._tasks = task_repository

    async def execute(
        self, fmt: str = "json", status: TaskStatus | None = None
    ) -> str:
        if fmt not in ("json", "csv"):
            from domain.errors import SchemaError

            raise SchemaError(f"Unsupported export format: {fmt!r}")
        tasks = await self._tasks.list(status)
        return self._serialize(tasks, fmt)

    @staticmethod
    def _serialize(tasks: list[ExtractionTask], fmt: str) -> str:
        if fmt == "csv":
            return ExportTasksUseCase._to_csv(tasks)
        return ExportTasksUseCase._to_json(tasks)

    @staticmethod
    def _to_json(tasks: list[ExtractionTask]) -> str:
        return json.dumps(
            [task.model_dump(mode="json") for task in tasks],
            indent=2,
            default=str,
        )

    @staticmethod
    def _to_csv(tasks: list[ExtractionTask]) -> str:
        import csv
        from io import StringIO

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "status",
                "created_at",
                "updated_at",
                "schema_validation_success",
                "retry_count",
                "latency_ms",
                "model_used",
                "review_notes",
                "extracted_fields",
                "error_diagnostic",
            ]
        )
        for task in tasks:
            payload = task.extracted_payload
            fields = (
                json.dumps(payload.fields, default=str, sort_keys=True)
                if payload is not None
                else ""
            )
            metrics = task.metrics
            writer.writerow(
                [
                    task.id,
                    task.status.value,
                    task.created_at.isoformat() if task.created_at else "",
                    task.updated_at.isoformat() if task.updated_at else "",
                    payload.schema_validation_success if payload is not None else "",
                    metrics.retry_count if metrics is not None else "",
                    metrics.latency_ms if metrics is not None else "",
                    metrics.model_used if metrics is not None else "",
                    task.review_notes or "",
                    fields,
                    task.error_diagnostic or "",
                ]
            )
        return buffer.getvalue()


class MetricsUseCase:
    """Aggregate observability metrics across all persisted tasks."""

    def __init__(self, metrics_repository: MetricsRepository) -> None:
        self._metrics = metrics_repository

    async def execute(self) -> dict[str, Any]:
        return await self._metrics.aggregate()
