"""FastAPI routers.

Endpoints translate HTTP DTOs into application use-case calls and back. No
extraction, persistence, or validation logic lives in this layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from application.use_cases import CreateTaskCommand, TaskFilters
from domain.schemas import ReviewAction, ReviewDecision, TaskStatus
from presentation.deps import (
    get_create_use_case,
    get_export_use_case,
    get_list_use_case,
    get_metrics_use_case,
    get_review_use_case,
    get_task_use_case,
)
from presentation.dto import (
    MetricsResponse,
    ReviewRequest,
    TaskCreateRequest,
    TaskResponse,
)

router = APIRouter(prefix="/api", tags=["tasks"])


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=201,
    summary="Create and run a structured extraction task",
)
async def create_task(
    request: TaskCreateRequest,
    use_case=Depends(get_create_use_case),
) -> TaskResponse:
    """Create a task, run extraction, and persist the structured result."""
    task = await use_case.execute(
        CreateTaskCommand(
            input_text=request.input_text,
            schema=request.schema,
            max_retries=request.max_retries,
        )
    )
    return TaskResponse.from_domain(task)


# NOTE: /tasks/export must be registered before /tasks/{task_id} so the literal
# path is not captured as a task id.
@router.get(
    "/tasks/export",
    summary="Export tasks as JSON or CSV",
)
async def export_tasks(
    response: Response,
    use_case=Depends(get_export_use_case),
    fmt: str = Query(default="json", pattern="^(json|csv)$"),
    status: TaskStatus | None = Query(default=None),
) -> Response:
    """Export all (or filtered) tasks. Handles an empty dataset cleanly."""
    content = await use_case.execute(fmt=fmt, status=status)
    media_type = "text/csv" if fmt == "csv" else "application/json"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="tasks_export.{fmt}"'
    )
    return Response(content=content, media_type=media_type)


@router.get(
    "/tasks",
    response_model=list[TaskResponse],
    summary="List/filter extraction tasks",
)
async def list_tasks(
    use_case=Depends(get_list_use_case),
    status: TaskStatus | None = Query(default=None),
) -> list[TaskResponse]:
    """List tasks optionally filtered by status."""
    tasks = await use_case.execute(TaskFilters(status=status))
    return [TaskResponse.from_domain(task) for task in tasks]


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Inspect a task and its metrics",
)
async def get_task(
    task_id: str,
    use_case=Depends(get_task_use_case),
) -> TaskResponse:
    """Fetch a single task by id, including its extracted fields and metrics."""
    task = await use_case.execute(task_id)
    return TaskResponse.from_domain(task)


@router.patch(
    "/tasks/{task_id}/review",
    response_model=TaskResponse,
    summary="Edit fields and approve/reject a task",
)
async def review_task(
    task_id: str,
    request: ReviewRequest,
    use_case=Depends(get_review_use_case),
) -> TaskResponse:
    """Apply human-in-the-loop edits and a review decision."""
    action = ReviewAction(
        decision=ReviewDecision(request.decision),
        fields=request.fields,
        notes=request.notes,
        reviewer=request.reviewer,
    )
    task = await use_case.execute(task_id, action)
    return TaskResponse.from_domain(task)


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    tags=["metrics"],
    summary="Aggregated observability statistics",
)
async def get_metrics(
    use_case=Depends(get_metrics_use_case),
) -> MetricsResponse:
    """Return aggregate metrics, including empty-state-safe rates."""
    return MetricsResponse(**(await use_case.execute()))
