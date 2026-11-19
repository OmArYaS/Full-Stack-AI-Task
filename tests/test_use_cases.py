"""Application use-case tests (extraction, review, export, metrics)."""

from __future__ import annotations

from typing import Any

import pytest

from application.use_cases import (
    CreateTaskCommand,
    CreateExtractionTaskUseCase,
    ExportTasksUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    MetricsUseCase,
    ReviewTaskUseCase,
    TaskFilters,
)
from domain.errors import (
    EmptyInputError,
    InputTooLongError,
    InvalidStatusTransitionError,
    LLMUnreachableError,
    TaskNotFoundError,
)
from domain.schemas import ReviewAction, ReviewDecision, TaskStatus
from infrastructure.extractor import ResilientJsonParser
from tests.conftest import (
    FakeLLMProvider,
    InMemoryMetricsRepository,
    InMemoryTaskRepository,
    VALID_JSON,
)


@pytest.fixture
def create_uc(
    fake_llm: FakeLLMProvider,
    task_repo: InMemoryTaskRepository,
    metrics_repo: InMemoryMetricsRepository,
    schema: dict[str, Any],
) -> CreateExtractionTaskUseCase:
    return CreateExtractionTaskUseCase(
        fake_llm,
        task_repo,
        metrics_repo,
        ResilientJsonParser(),
        max_input_length=500,
        default_schema=schema,
        default_max_retries=2,
    )


async def test_create_task_success(create_uc: CreateExtractionTaskUseCase, task_repo: InMemoryTaskRepository) -> None:
    task = await create_uc.execute(CreateTaskCommand(input_text="Ada wrote some code."))
    assert task.id
    assert task.status is TaskStatus.PENDING_REVIEW
    assert task.extracted_payload is not None
    assert task.extracted_payload.fields["summary"] == "A short summary"
    assert task.extracted_payload.schema_validation_success is True
    assert task.metrics is not None
    assert task.metrics.model_used == "fake-model"
    assert task.metrics.schema_validation_success is True
    assert task.metrics.latency_ms >= 0
    assert await task_repo.get(task.id) is not None


async def test_create_task_strips_think_and_fences(
    fake_llm: FakeLLMProvider, create_uc: CreateExtractionTaskUseCase
) -> None:
    fake_llm.set_response(
        "<think>thinking...</think>\n```json\n" + VALID_JSON + "\n```"
    )
    task = await create_uc.execute(CreateTaskCommand(input_text="Some input text"))
    assert task.status is TaskStatus.PENDING_REVIEW
    assert task.extracted_payload is not None
    assert task.extracted_payload.fields["entities"] == ["Ada"]


@pytest.mark.parametrize("text", ["", "   ", "\n\t  "])
async def test_empty_input_rejected(
    create_uc: CreateExtractionTaskUseCase, text: str
) -> None:
    with pytest.raises(EmptyInputError):
        await create_uc.execute(CreateTaskCommand(input_text=text))


async def test_oversized_input_rejected(create_uc: CreateExtractionTaskUseCase) -> None:
    with pytest.raises(InputTooLongError) as exc:
        await create_uc.execute(CreateTaskCommand(input_text="x" * 501))
    assert exc.value.length == 501
    assert exc.value.maximum == 500


async def test_unparseable_output_marks_failed_validation(
    fake_llm: FakeLLMProvider, create_uc: CreateExtractionTaskUseCase
) -> None:
    fake_llm.set_response("<think>confused</think> not json")
    task = await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    assert task.status is TaskStatus.FAILED_VALIDATION
    assert task.extracted_payload is not None
    assert task.extracted_payload.fields == {}
    assert task.error_diagnostic
    assert "unparseable JSON" in task.error_diagnostic
    assert task.metrics is not None
    assert task.metrics.retry_count == 3  # initial + 2 retries


async def test_schema_invalid_output_marks_needs_manual_fix(
    fake_llm: FakeLLMProvider, create_uc: CreateExtractionTaskUseCase
) -> None:
    fake_llm.set_response('{"summary": 42}')
    task = await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    assert task.status is TaskStatus.NEEDS_MANUAL_FIX
    assert task.extracted_payload is not None
    assert task.extracted_payload.fields == {"summary": 42}
    assert task.error_diagnostic and "schema validation failed" in task.error_diagnostic


async def test_unreachable_llm_raises_domain_error(
    fake_llm: FakeLLMProvider,
    create_uc: CreateExtractionTaskUseCase,
    task_repo: InMemoryTaskRepository,
) -> None:
    fake_llm.set_error(LLMUnreachableError("http://localhost:11434"))
    with pytest.raises(LLMUnreachableError):
        await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    tasks = await task_repo.list()
    assert len(tasks) == 1
    assert tasks[0].status is TaskStatus.FAILED_VALIDATION
    assert "LLM provider call failed" in (tasks[0].error_diagnostic or "")


async def test_max_retries_zero_is_respected(
    fake_llm: FakeLLMProvider, create_uc: CreateExtractionTaskUseCase
) -> None:
    fake_llm.set_response("not json")
    task = await create_uc.execute(
        CreateTaskCommand(input_text="Some text", max_retries=0)
    )
    assert task.metrics is not None
    assert task.metrics.retry_count == 1  # only the initial attempt


async def test_get_task_and_missing_task(
    task_repo: InMemoryTaskRepository,
    create_uc: CreateExtractionTaskUseCase,
) -> None:
    task = await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    use_case = GetTaskUseCase(task_repo)
    assert (await use_case.execute(task.id or "")).id == task.id
    with pytest.raises(TaskNotFoundError):
        await use_case.execute("missing-id")


async def test_list_tasks_filters_by_status(
    task_repo: InMemoryTaskRepository,
    create_uc: CreateExtractionTaskUseCase,
) -> None:
    await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    use_case = ListTasksUseCase(task_repo)
    assert len(await use_case.execute(TaskFilters())) == 1
    assert len(await use_case.execute(TaskFilters(status=TaskStatus.PENDING_REVIEW))) == 1
    assert len(await use_case.execute(TaskFilters(status=TaskStatus.APPROVED))) == 0


async def test_review_approve_with_field_edits(
    task_repo: InMemoryTaskRepository,
    create_uc: CreateExtractionTaskUseCase,
) -> None:
    task = await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    use_case = ReviewTaskUseCase(task_repo)
    updated = await use_case.execute(
        task.id or "",
        ReviewAction(
            decision=ReviewDecision.APPROVED,
            fields={"summary": "edited by human"},
            notes="Verified manually",
            reviewer="alice",
        ),
    )
    assert updated.status is TaskStatus.APPROVED
    assert updated.extracted_payload is not None
    assert updated.extracted_payload.fields["summary"] == "edited by human"
    assert updated.review_notes == "Verified manually"
    assert updated.reviewed_by == "alice"
    assert (await task_repo.get(task.id or "")).status is TaskStatus.APPROVED


async def test_review_reject_with_notes(
    task_repo: InMemoryTaskRepository,
    create_uc: CreateExtractionTaskUseCase,
) -> None:
    task = await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    updated = await ReviewTaskUseCase(task_repo).execute(
        task.id or "",
        ReviewAction(decision=ReviewDecision.REJECTED, notes="Bad extraction"),
    )
    assert updated.status is TaskStatus.REJECTED
    assert updated.review_notes == "Bad extraction"


async def test_review_missing_task(
    task_repo: InMemoryTaskRepository,
) -> None:
    with pytest.raises(TaskNotFoundError):
        await ReviewTaskUseCase(task_repo).execute(
            "does-not-exist", ReviewAction(decision=ReviewDecision.APPROVED)
        )


async def test_review_invalid_status_transition(
    task_repo: InMemoryTaskRepository,
    create_uc: CreateExtractionTaskUseCase,
) -> None:
    task = await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    use_case = ReviewTaskUseCase(task_repo)
    await use_case.execute(
        task.id or "", ReviewAction(decision=ReviewDecision.APPROVED)
    )
    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(
            task.id or "", ReviewAction(decision=ReviewDecision.REJECTED)
        )


async def test_export_empty_json_and_csv(task_repo: InMemoryTaskRepository) -> None:
    use_case = ExportTasksUseCase(task_repo)
    assert await use_case.execute(fmt="json") == "[]"
    csv_text = await use_case.execute(fmt="csv")
    assert csv_text.strip().startswith("id,status")


async def test_export_filtered_records(
    task_repo: InMemoryTaskRepository, create_uc: CreateExtractionTaskUseCase
) -> None:
    task = await create_uc.execute(CreateTaskCommand(input_text="Some text"))
    await ReviewTaskUseCase(task_repo).execute(
        task.id or "", ReviewAction(decision=ReviewDecision.APPROVED)
    )
    use_case = ExportTasksUseCase(task_repo)
    import json

    all_json = json.loads(await use_case.execute(fmt="json"))
    approved_json = json.loads(
        await use_case.execute(fmt="json", status=TaskStatus.APPROVED)
    )
    rejected_json = json.loads(
        await use_case.execute(fmt="json", status=TaskStatus.REJECTED)
    )
    assert len(all_json) == 1
    assert len(approved_json) == 1
    assert rejected_json == []


async def test_metrics_empty_state(
    metrics_repo: InMemoryMetricsRepository,
) -> None:
    result = await MetricsUseCase(metrics_repo).execute()
    assert result["total_tasks"] == 0
    assert result["schema_validation_success_rate"] == 0.0
    assert result["avg_latency_ms"] == 0.0
    assert result["avg_retry_count"] == 0.0
    assert all(count == 0 for count in result["status_counts"].values())


async def test_metrics_math(
    metrics_repo: InMemoryMetricsRepository,
    create_uc: CreateExtractionTaskUseCase,
    fake_llm: FakeLLMProvider,
) -> None:
    await create_uc.execute(CreateTaskCommand(input_text="First text"))
    fake_llm.set_response('{"summary": 99}')
    await create_uc.execute(CreateTaskCommand(input_text="Second text"))
    result = await MetricsUseCase(metrics_repo).execute()
    assert result["total_tasks"] == 2
    assert result["schema_validation_success_count"] == 1
    assert result["schema_validation_success_rate"] == 0.5
    assert result["tasks_with_metrics"] == 2
    assert result["models_used"] == ["fake-model"]
