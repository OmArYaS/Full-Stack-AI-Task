"""FastAPI dependency providers.

All dependencies resolve through ``app.state.container``. Tests can override
the port-level dependencies (``get_llm_provider``, ``get_task_repository``,
``get_metrics_repository``) with in-memory fakes for fully offline testing.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request

from application.use_cases import (
    CreateExtractionTaskUseCase,
    ExportTasksUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    MetricsUseCase,
    ReviewTaskUseCase,
)
from domain.ports import (
    LLMProvider,
    MetricsRepository,
    StructuredOutputParser,
    TaskRepository,
)


def get_container(request: Request) -> Any:
    """Return the composition root attached to the app."""
    return request.app.state.container


def get_settings(request: Request) -> Any:
    """Return runtime settings."""
    return get_container(request).settings


def get_llm_provider(request: Request) -> LLMProvider:
    """Return the configured LLM provider adapter."""
    return get_container(request).llm_provider


def get_task_repository(request: Request) -> TaskRepository:
    """Return the configured task repository adapter."""
    return get_container(request).task_repository


def get_metrics_repository(request: Request) -> MetricsRepository:
    """Return the configured metrics repository adapter."""
    return get_container(request).metrics_repository


def get_output_parser(request: Request) -> StructuredOutputParser:
    """Return the configured structured-output parser adapter."""
    return get_container(request).output_parser


def get_create_use_case(
    llm: LLMProvider = Depends(get_llm_provider),
    tasks: TaskRepository = Depends(get_task_repository),
    metrics: MetricsRepository = Depends(get_metrics_repository),
    parser: StructuredOutputParser = Depends(get_output_parser),
    settings: Any = Depends(get_settings),
) -> CreateExtractionTaskUseCase:
    """Build the create/extract use case from injected adapters."""
    return CreateExtractionTaskUseCase(
        llm,
        tasks,
        metrics,
        parser,
        max_input_length=settings.MAX_INPUT_LENGTH,
        default_schema=settings.DEFAULT_SCHEMA,
        default_max_retries=settings.DEFAULT_MAX_RETRIES,
    )


def get_task_use_case(
    tasks: TaskRepository = Depends(get_task_repository),
) -> GetTaskUseCase:
    return GetTaskUseCase(tasks)


def get_list_use_case(
    tasks: TaskRepository = Depends(get_task_repository),
) -> ListTasksUseCase:
    return ListTasksUseCase(tasks)


def get_review_use_case(
    tasks: TaskRepository = Depends(get_task_repository),
) -> ReviewTaskUseCase:
    return ReviewTaskUseCase(tasks)


def get_export_use_case(
    tasks: TaskRepository = Depends(get_task_repository),
) -> ExportTasksUseCase:
    return ExportTasksUseCase(tasks)


def get_metrics_use_case(
    metrics: MetricsRepository = Depends(get_metrics_repository),
) -> MetricsUseCase:
    return MetricsUseCase(metrics)
