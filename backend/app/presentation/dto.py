"""HTTP request/response DTOs.

These are deliberately separate from domain schemas so the HTTP contract can
evolve without touching domain/application logic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.schemas import ExtractionTask


class _HTTPModel(BaseModel):
    """Base DTO configured to allow the 'schema' field name."""

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class TaskCreateRequest(_HTTPModel):
    """Body for ``POST /api/tasks``."""

    input_text: str = Field(..., description="Unstructured text to extract from.")
    task_schema: dict[str, Any] | None = Field(
        default=None, alias="schema", description="Optional JSON Schema."
    )

    @property
    def schema(self) -> dict[str, Any] | None:
        """Optional JSON Schema supplied by the caller."""
        return self.task_schema

    max_retries: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Bounded schema-repair retry count (default 2).",
    )


class ReviewRequest(_HTTPModel):
    """Body for ``PATCH /api/tasks/{task_id}/review``."""

    decision: Literal["approved", "rejected"]
    fields: dict[str, Any] | None = Field(
        default=None, description="Manually edited field values to merge."
    )
    notes: str | None = Field(default=None, description="Review notes.")
    reviewer: str | None = Field(default=None, description="Reviewer identity.")


class MetricsResponse(_HTTPModel):
    """Aggregated observability statistics."""

    total_tasks: int
    status_counts: dict[str, int]
    tasks_with_metrics: int
    schema_validation_success_count: int
    schema_validation_success_rate: float
    avg_latency_ms: float
    total_retries: int
    avg_retry_count: float
    models_used: list[str]


class HealthResponse(_HTTPModel):
    """Health-check response."""

    status: str
    service: str


class TaskResponse(_HTTPModel):
    """A task as returned by the API."""

    id: str
    input_text: str
    task_schema: dict[str, Any] = Field(alias="schema")
    status: str
    extracted_payload: dict[str, Any] | None
    created_at: str | None
    updated_at: str | None
    review_notes: str | None
    reviewed_by: str | None
    metrics: dict[str, Any] | None
    error_diagnostic: str | None

    @property
    def schema(self) -> dict[str, Any]:
        """JSON Schema describing the task's extraction shape."""
        return self.task_schema

    @classmethod
    def from_domain(cls, task: ExtractionTask) -> "TaskResponse":
        """Map a domain task to the HTTP response DTO."""
        return cls(
            id=task.id or "",
            input_text=task.input_text,
            schema=task.schema,
            status=task.status.value,
            extracted_payload=(
                task.extracted_payload.model_dump(mode="json")
                if task.extracted_payload
                else None
            ),
            created_at=task.created_at.isoformat() if task.created_at else None,
            updated_at=task.updated_at.isoformat() if task.updated_at else None,
            review_notes=task.review_notes,
            reviewed_by=task.reviewed_by,
            metrics=task.metrics.model_dump(mode="json") if task.metrics else None,
            error_diagnostic=task.error_diagnostic,
        )
