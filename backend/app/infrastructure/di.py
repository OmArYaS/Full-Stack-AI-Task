"""Dependency-injection wiring.

This is the single place where concrete adapters are bound to domain ports and
application use cases. Swapping Ollama for another LLM provider (or SQLite for
another store) only requires changing this module — never domain or application.
"""

from __future__ import annotations

from domain.ports import (
    LLMProvider,
    MetricsRepository,
    StructuredOutputParser,
    TaskRepository,
)
from infrastructure.config import Settings
from infrastructure.extractor import ResilientJsonParser
from infrastructure.ollama_provider import OllamaLLMProvider
from infrastructure.sqlite_repo import SQLiteMetricsRepository, SQLiteTaskRepository

from application.use_cases import (
    CreateExtractionTaskUseCase,
    ExportTasksUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    MetricsUseCase,
    ReviewTaskUseCase,
)


class Container:
    """Composition root holding adapter instances and use-case factories."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

        self.llm_provider: LLMProvider = OllamaLLMProvider(
            base_url=self.settings.OLLAMA_BASE_URL,
            model=self.settings.OLLAMA_MODEL,
            timeout=self.settings.OLLAMA_TIMEOUT,
        )
        self.task_repository: TaskRepository = SQLiteTaskRepository(
            self.settings.DB_PATH
        )
        self.metrics_repository: MetricsRepository = SQLiteMetricsRepository(
            self.settings.DB_PATH
        )
        self.output_parser: StructuredOutputParser = ResilientJsonParser()

    def create_task_use_case(self) -> CreateExtractionTaskUseCase:
        return CreateExtractionTaskUseCase(
            self.llm_provider,
            self.task_repository,
            self.metrics_repository,
            self.output_parser,
            max_input_length=self.settings.MAX_INPUT_LENGTH,
            default_schema=self.settings.DEFAULT_SCHEMA,
            default_max_retries=self.settings.DEFAULT_MAX_RETRIES,
        )

    def get_task_use_case(self) -> GetTaskUseCase:
        return GetTaskUseCase(self.task_repository)

    def list_task_use_case(self) -> ListTasksUseCase:
        return ListTasksUseCase(self.task_repository)

    def review_task_use_case(self) -> ReviewTaskUseCase:
        return ReviewTaskUseCase(self.task_repository)

    def export_task_use_case(self) -> ExportTasksUseCase:
        return ExportTasksUseCase(self.task_repository)

    def metrics_use_case(self) -> MetricsUseCase:
        return MetricsUseCase(self.metrics_repository)


def build_container(settings: Settings | None = None) -> Container:
    """Build a fresh composition root."""
    return Container(settings)
