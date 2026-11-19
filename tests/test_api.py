"""End-to-end FastAPI endpoint tests using mocked LLM adapters (offline)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from domain.errors import LLMUnreachableError
from tests.conftest import FakeLLMProvider, InMemoryTaskRepository, VALID_JSON


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "extraction-copilot-backend",
    }


def test_create_task_endpoint_returns_structured_payload(client: TestClient) -> None:
    response = client.post(
        "/api/tasks", json={"input_text": "Ada wrote some code."}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending_review"
    assert data["extracted_payload"]["fields"]["summary"] == "A short summary"
    assert data["metrics"]["schema_validation_success"] is True
    assert data["metrics"]["model_used"] == "fake-model"
    assert data["id"]


def test_create_task_strips_think_and_fences(
    client: TestClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.set_response(
        "<think>reasoning...</think>\n```json\n" + VALID_JSON + "\n```"
    )
    response = client.post("/api/tasks", json={"input_text": "Unstructured text"})
    assert response.status_code == 201
    assert response.json()["status"] == "pending_review"


def test_create_task_empty_input_returns_422(client: TestClient) -> None:
    for text in ("", "   ", "\n\t"):
        response = client.post("/api/tasks", json={"input_text": text})
        assert response.status_code == 422
        assert response.json()["error"] == "EmptyInputError"


def test_create_task_oversized_input_returns_422(client: TestClient) -> None:
    response = client.post("/api/tasks", json={"input_text": "x" * 501})
    assert response.status_code == 422
    assert response.json()["error"] == "InputTooLongError"
    assert "500" in response.json()["message"]


def test_create_task_unreachable_llm_returns_502(
    client: TestClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.set_error(LLMUnreachableError("http://localhost:11434"))
    response = client.post("/api/tasks", json={"input_text": "Some text"})
    assert response.status_code == 502
    assert response.json()["error"] == "LLMUnreachableError"


def test_malformed_output_is_persisted_with_diagnostic(
    client: TestClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.set_response("<think>bad output</think> not json")
    response = client.post("/api/tasks", json={"input_text": "Some text"})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "failed_validation"
    assert "unparseable JSON" in (data["error_diagnostic"] or "")
    assert data["metrics"]["retry_count"] == 3


def test_list_tasks_and_status_filter(client: TestClient) -> None:
    assert client.get("/api/tasks").json() == []
    created = client.post("/api/tasks", json={"input_text": "Some text"}).json()
    listed = client.get("/api/tasks").json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]
    assert len(client.get("/api/tasks", params={"status": "pending_review"}).json()) == 1
    assert client.get("/api/tasks", params={"status": "approved"}).json() == []
    bad = client.get("/api/tasks", params={"status": "not-a-status"})
    assert bad.status_code == 422


def test_get_task_detail_and_missing(client: TestClient) -> None:
    task_id = client.post("/api/tasks", json={"input_text": "Some text"}).json()["id"]
    response = client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["id"] == task_id
    assert client.get("/api/tasks/missing-id").status_code == 404


def test_review_endpoint_edits_and_approves(
    client: TestClient, task_repo: InMemoryTaskRepository
) -> None:
    task_id = client.post("/api/tasks", json={"input_text": "Some text"}).json()["id"]
    response = client.patch(
        f"/api/tasks/{task_id}/review",
        json={
            "decision": "approved",
            "fields": {"summary": "human-edited"},
            "notes": "Verified",
            "reviewer": "alice",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["extracted_payload"]["fields"]["summary"] == "human-edited"
    assert data["review_notes"] == "Verified"
    assert data["reviewed_by"] == "alice"
    assert run_repo(task_repo, task_id) == "approved"

    # Terminal status cannot be reviewed again.
    again = client.patch(
        f"/api/tasks/{task_id}/review", json={"decision": "rejected"}
    )
    assert again.status_code == 400


def test_review_missing_task(client: TestClient) -> None:
    response = client.patch(
        "/api/tasks/missing-id/review", json={"decision": "approved"}
    )
    assert response.status_code == 404
    assert response.json()["error"] == "TaskNotFoundError"


def test_export_json_and_csv_empty_and_populated(client: TestClient) -> None:
    empty_json = client.get("/api/tasks/export")
    assert empty_json.status_code == 200
    assert empty_json.json() == []

    empty_csv = client.get("/api/tasks/export", params={"fmt": "csv"})
    assert empty_csv.status_code == 200
    assert empty_csv.text.strip().startswith("id,status")

    client.post("/api/tasks", json={"input_text": "Some text"})
    exported = client.get("/api/tasks/export")
    assert len(exported.json()) == 1
    csv_text = client.get(
        "/api/tasks/export", params={"fmt": "csv", "status": "pending_review"}
    ).text
    assert "pending_review" in csv_text
    assert client.get("/api/tasks/export", params={"fmt": "xml"}).status_code == 422


def test_metrics_endpoint_empty_and_populated(client: TestClient) -> None:
    empty = client.get("/api/metrics").json()
    assert empty["total_tasks"] == 0
    assert empty["schema_validation_success_rate"] == 0.0
    assert empty["avg_latency_ms"] == 0.0

    client.post("/api/tasks", json={"input_text": "Some text"})
    populated: dict[str, Any] = client.get("/api/metrics").json()
    assert populated["total_tasks"] == 1
    assert populated["status_counts"]["pending_review"] == 1
    assert populated["schema_validation_success_count"] == 1
    assert populated["schema_validation_success_rate"] == 1.0
    assert "fake-model" in populated["models_used"]


def test_openapi_contract_exposes_endpoints(client: TestClient) -> None:
    schema_doc = client.get("/openapi.json").json()
    paths = schema_doc["paths"]
    for path in (
        "/api/tasks",
        "/api/tasks/export",
        "/api/tasks/{task_id}",
        "/api/tasks/{task_id}/review",
        "/api/metrics",
        "/health",
    ):
        assert path in paths


def run_repo(repo: InMemoryTaskRepository, task_id: str) -> str:
    """Read a task's status synchronously for assertions."""
    import asyncio

    task = asyncio.run(repo.get(task_id))
    assert task is not None
    return task.status.value
