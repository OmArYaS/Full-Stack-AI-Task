"""Domain-layer unit tests (pure schemas and errors)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.errors import (
    DomainError,
    InvalidStatusTransitionError,
    TaskNotFoundError,
)
from domain.schemas import (
    ExtractionMetrics,
    ExtractionTask,
    ExtractedPayload,
    ReviewAction,
    ReviewDecision,
    TaskStatus,
)


def test_task_status_values_and_properties() -> None:
    assert {status.value for status in TaskStatus} == {
        "pending_review",
        "approved",
        "rejected",
        "failed_validation",
        "needs_manual_fix",
    }
    assert TaskStatus.APPROVED.is_terminal
    assert TaskStatus.REJECTED.is_terminal
    assert not TaskStatus.PENDING_REVIEW.is_terminal
    assert TaskStatus.PENDING_REVIEW.is_reviewable
    assert TaskStatus.NEEDS_MANUAL_FIX.is_reviewable
    assert not TaskStatus.APPROVED.is_reviewable


def test_review_decision_values() -> None:
    assert ReviewDecision.APPROVED.value == "approved"
    assert ReviewDecision.REJECTED.value == "rejected"


def test_extraction_metrics_validation() -> None:
    metrics = ExtractionMetrics(
        latency_ms=12.5,
        retry_count=0,
        schema_validation_success=True,
        model_used="qwen2.5:7b-instruct-q4_k_m",
    )
    assert metrics.latency_ms == 12.5
    with pytest.raises(ValidationError):
        ExtractionMetrics(
            latency_ms=-1,
            retry_count=0,
            schema_validation_success=True,
            model_used="m",
        )
    with pytest.raises(ValidationError):
        ExtractionMetrics(
            latency_ms=1,
            retry_count=-1,
            schema_validation_success=True,
            model_used="m",
        )


def test_extracted_payload_defaults() -> None:
    payload = ExtractedPayload()
    assert payload.fields == {}
    assert payload.raw_llm_response == ""
    assert payload.schema_validation_success is False


def test_extraction_task_defaults_and_schema_field() -> None:
    task = ExtractionTask(input_text="hello", schema={"type": "object"})
    assert task.status is TaskStatus.PENDING_REVIEW
    assert task.id is None
    assert task.extracted_payload is None
    assert task.metrics is None
    assert task.schema == {"type": "object"}
    dumped = task.model_dump(mode="json")
    assert dumped["schema"] == {"type": "object"}


def test_review_action_model() -> None:
    action = ReviewAction(
        decision=ReviewDecision.APPROVED,
        fields={"summary": "edited"},
        notes="looks good",
        reviewer="alice",
    )
    assert action.fields == {"summary": "edited"}
    assert action.notes == "looks good"


def test_domain_errors_carry_details() -> None:
    missing = TaskNotFoundError("abc")
    assert missing.task_id == "abc"
    assert "abc" in str(missing)
    transition = InvalidStatusTransitionError("approved", "pending_review")
    assert transition.current == "approved"
    assert transition.target == "pending_review"
    assert isinstance(missing, DomainError)
