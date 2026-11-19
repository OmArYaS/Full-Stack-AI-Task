"""SQLite adapters implementing the domain repository ports.

Persistence uses the Python standard-library ``sqlite3`` module. Blocking
database calls are offloaded with :func:`asyncio.to_thread` so async endpoints
never block the event loop. No ORM or vendor framework is required.
"""

from __future__ import annotations

import asyncio
import csv
import json
import sqlite3
import uuid
from io import StringIO
from pathlib import Path
from typing import Any

from domain.ports import MetricsRepository, TaskRepository
from domain.schemas import (
    ExtractionMetrics,
    ExtractionTask,
    ExtractedPayload,
    TaskStatus,
)


def _json_dumps(value: Any) -> str:
    """Serialize a value to a JSON string."""
    return json.dumps(value, default=str)


def _json_loads(value: str | None, fallback: Any) -> Any:
    """Deserialize a JSON string, returning ``fallback`` when empty/invalid."""
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


class _SQLiteBase:
    """Shared SQLite connection/schema setup for the two repositories."""

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        parent = Path(self.db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        """Create tables if they do not yet exist."""

        def create() -> None:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id                TEXT PRIMARY KEY,
                        input_text        TEXT NOT NULL,
                        schema_json       TEXT NOT NULL,
                        status            TEXT NOT NULL,
                        payload_json      TEXT,
                        created_at        TEXT,
                        updated_at        TEXT,
                        review_notes      TEXT,
                        reviewed_by       TEXT,
                        error_diagnostic  TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_metrics (
                        id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id                   TEXT NOT NULL,
                        latency_ms                REAL NOT NULL,
                        retry_count               INTEGER NOT NULL,
                        schema_validation_success INTEGER NOT NULL,
                        model_used                TEXT NOT NULL,
                        recorded_at               TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_metrics_task ON task_metrics(task_id)"
                )

        # DDL is fast and only runs once at construction; no need to offload.
        create()


class SQLiteTaskRepository(_SQLiteBase, TaskRepository):
    """Persist extraction tasks in SQLite."""

    def _metrics_for(self, connection: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM task_metrics WHERE task_id = ? "
            "ORDER BY recorded_at DESC, id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "latency_ms": float(row["latency_ms"]),
            "retry_count": int(row["retry_count"]),
            "schema_validation_success": bool(row["schema_validation_success"]),
            "model_used": row["model_used"],
        }

    def _row_to_task(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> ExtractionTask:
        payload_data = _json_loads(row["payload_json"], None)
        payload = ExtractedPayload(**payload_data) if payload_data else None
        metrics_data = self._metrics_for(connection, row["id"])
        metrics = ExtractionMetrics(**metrics_data) if metrics_data else None
        from datetime import datetime

        created = datetime.fromisoformat(row["created_at"]) if row["created_at"] else None
        updated = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None
        return ExtractionTask(
            id=row["id"],
            input_text=row["input_text"],
            schema=_json_loads(row["schema_json"], {}),
            status=TaskStatus(row["status"]),
            extracted_payload=payload,
            created_at=created,
            updated_at=updated,
            review_notes=row["review_notes"],
            reviewed_by=row["reviewed_by"],
            metrics=metrics,
            error_diagnostic=row["error_diagnostic"],
        )

    def _add_sync(self, task: ExtractionTask) -> ExtractionTask:
        task_id = task.id or str(uuid.uuid4())
        created_at = _iso(task.created_at)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, input_text, schema_json, status, payload_json,
                    created_at, updated_at, review_notes, reviewed_by,
                    error_diagnostic
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task.input_text,
                    _json_dumps(task.schema),
                    task.status.value,
                    _json_dumps(task.extracted_payload.model_dump(mode="json"))
                    if task.extracted_payload
                    else None,
                    created_at,
                    _iso(task.updated_at) or created_at,
                    task.review_notes,
                    task.reviewed_by,
                    task.error_diagnostic,
                ),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            saved = self._row_to_task(connection, row)
        return saved

    def _get_sync(self, task_id: str) -> ExtractionTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return self._row_to_task(connection, row) if row else None

    def _list_sync(self, status: TaskStatus | None) -> list[ExtractionTask]:
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC, id DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM tasks WHERE status = ? "
                    "ORDER BY created_at DESC, id DESC",
                    (status.value,),
                ).fetchall()
            return [self._row_to_task(connection, row) for row in rows]

    def _update_sync(self, task: ExtractionTask) -> ExtractionTask:
        task_id = task.id or ""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks SET
                    status = ?, payload_json = ?, updated_at = ?,
                    review_notes = ?, reviewed_by = ?, error_diagnostic = ?
                WHERE id = ?
                """,
                (
                    task.status.value,
                    _json_dumps(task.extracted_payload.model_dump(mode="json"))
                    if task.extracted_payload
                    else None,
                    _iso(task.updated_at),
                    task.review_notes,
                    task.reviewed_by,
                    task.error_diagnostic,
                    task_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return self._row_to_task(connection, row)

    async def add(self, task: ExtractionTask) -> ExtractionTask:
        return await asyncio.to_thread(self._add_sync, task)

    async def get(self, task_id: str) -> ExtractionTask | None:
        return await asyncio.to_thread(self._get_sync, task_id)

    async def list(self, status: TaskStatus | None = None) -> list[ExtractionTask]:
        return await asyncio.to_thread(self._list_sync, status)

    async def update(self, task: ExtractionTask) -> ExtractionTask:
        return await asyncio.to_thread(self._update_sync, task)

    async def export(
        self, status: TaskStatus | None = None, fmt: str = "json"
    ) -> str:
        tasks = await self.list(status)
        if fmt == "csv":
            buffer = StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["id", "status", "extracted_fields", "error_diagnostic"])
            for task in tasks:
                fields = (
                    _json_dumps(task.extracted_payload.fields)
                    if task.extracted_payload
                    else ""
                )
                writer.writerow([task.id, task.status.value, fields, task.error_diagnostic or ""])
            return buffer.getvalue()
        return _json_dumps([task.model_dump(mode="json") for task in tasks])


class SQLiteMetricsRepository(_SQLiteBase, MetricsRepository):
    """Record per-task metrics and compute aggregated, empty-state-safe stats."""

    def _record_sync(self, task_id: str, metrics: ExtractionMetrics) -> None:
        from datetime import datetime, timezone

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_metrics (
                    task_id, latency_ms, retry_count,
                    schema_validation_success, model_used, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    metrics.latency_ms,
                    metrics.retry_count,
                    int(metrics.schema_validation_success),
                    metrics.model_used,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _aggregate_sync(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
            status_rows = connection.execute(
                "SELECT status, COUNT(*) AS c FROM tasks GROUP BY status"
            ).fetchall()
            status_counts = {
                status.value: 0 for status in TaskStatus
            }
            for row in status_rows:
                status_counts[row["status"]] = row["c"]

            metric_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS n,
                    COALESCE(AVG(latency_ms), 0.0) AS avg_latency,
                    COALESCE(SUM(retry_count), 0) AS total_retries,
                    COALESCE(AVG(retry_count), 0.0) AS avg_retries,
                    COALESCE(SUM(schema_validation_success), 0) AS successes
                FROM task_metrics
                """
            ).fetchone()
            model_rows = connection.execute(
                "SELECT DISTINCT model_used FROM task_metrics ORDER BY model_used"
            ).fetchall()

        n = int(metric_row["n"])
        # Guard division by zero for an empty dataset.
        success_count = int(metric_row["successes"])
        validation_rate = (success_count / n) if n else 0.0
        return {
            "total_tasks": int(total),
            "status_counts": status_counts,
            "tasks_with_metrics": n,
            "schema_validation_success_count": success_count,
            "schema_validation_success_rate": round(validation_rate, 4),
            "avg_latency_ms": round(float(metric_row["avg_latency"]), 2),
            "total_retries": int(metric_row["total_retries"]),
            "avg_retry_count": round(float(metric_row["avg_retries"]), 2),
            "models_used": [row["model_used"] for row in model_rows],
        }

    async def record(self, task_id: str, metrics: ExtractionMetrics) -> None:
        await asyncio.to_thread(self._record_sync, task_id, metrics)

    async def aggregate(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._aggregate_sync)
