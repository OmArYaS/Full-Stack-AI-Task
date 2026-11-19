"""Pure domain schemas.

All models are framework-agnostic Pydantic data structures used across the
domain, application, and infrastructure layers. They contain no FastAPI,
SQLAlchemy, or Ollama references.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Lifecycle status of an extraction task.

    Transitions:
        pending_review -> approved | rejected          (human review)
        needs_manual_fix -> pending_review | approved | rejected
        failed_validation -> approved | rejected        (after manual correction)
        approved / rejected are terminal.
    """

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED_VALIDATION = "failed_validation"
    NEEDS_MANUAL_FIX = "needs_manual_fix"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.APPROVED, TaskStatus.REJECTED)

    @property
    def is_reviewable(self) -> bool:
        return self in (
            TaskStatus.PENDING_REVIEW,
            TaskStatus.FAILED_VALIDATION,
            TaskStatus.NEEDS_MANUAL_FIX,
        )


class ReviewDecision(str, Enum):
    """Decision a human reviewer can make on a task."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ExtractionMetrics(BaseModel):
    """Per-task observability metrics recorded after extraction."""

    model_config = ConfigDict(frozen=False)

    latency_ms: float = Field(
        ge=0,
        description="End-to-end extraction latency in milliseconds.",
    )
    retry_count: int = Field(
        ge=0,
        description="Number of schema-repair retries performed before parsing.",
    )
    schema_validation_success: bool = Field(
        description="Whether the final payload validated against the schema.",
    )
    model_used: str = Field(
        description="LLM model identifier used for the extraction.",
    )


class ExtractedPayload(BaseModel):
    """The structured output extracted from unstructured text."""

    model_config = ConfigDict(frozen=False)

    fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted key/value fields conforming to the task schema.",
    )
    raw_llm_response: str = Field(
        default="",
        description="Raw response returned by the LLM provider (pre-stripping).",
    )
    schema_validation_success: bool = Field(
        default=False,
        description="Whether these fields passed schema validation.",
    )


class ExtractionTask(BaseModel):
    """An extraction task record flowing through the system."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    id: str | None = None
    input_text: str = Field(..., description="Unstructured input text to extract from.")
    # Exposed publicly as 'schema'; aliased to avoid shadowing BaseModel.schema.
    task_schema: dict[str, Any] = Field(
        default_factory=dict,
        alias="schema",
        description="JSON Schema describing the expected extraction shape.",
    )

    @property
    def schema(self) -> dict[str, Any]:
        """The JSON Schema describing this task's expected extraction shape."""
        return self.task_schema

    status: TaskStatus = TaskStatus.PENDING_REVIEW
    extracted_payload: ExtractedPayload | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    review_notes: str | None = Field(
        default=None,
        description="Human reviewer notes, if the task has been reviewed.",
    )
    reviewed_by: str | None = Field(
        default=None,
        description="Identity of the human reviewer, if reviewed.",
    )
    metrics: ExtractionMetrics | None = Field(
        default=None,
        description="Observability metrics captured during extraction.",
    )
    error_diagnostic: str | None = Field(
        default=None,
        description="Diagnostic details when extraction or validation failed.",
    )


class ReviewAction(BaseModel):
    """Input payload for a human-in-the-loop review decision."""

    model_config = ConfigDict(frozen=False)

    decision: ReviewDecision = Field(
        ..., description="Approve or reject the extracted payload."
    )
    fields: dict[str, Any] | None = Field(
        default=None,
        description="Manually edited field values to merge into the payload.",
    )
    notes: str | None = Field(default=None, description="Optional review notes.")
    reviewer: str | None = Field(default=None, description="Reviewer identity.")
