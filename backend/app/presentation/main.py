"""FastAPI application factory and health endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import Settings
from infrastructure.di import build_container
from presentation.dto import HealthResponse
from presentation.exceptions import add_error_handlers
from presentation.routers import router as api_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and wire a FastAPI application."""
    app = FastAPI(
        title="AI Task & Structured Extraction Copilot",
        version="1.0.0",
        description=(
            "Model-agnostic, local-first structured extraction with "
            "human-in-the-loop review and observability."
        ),
    )

    container = build_container(settings)
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # local development; lock down in production
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_error_handlers(app)
    app.include_router(api_router)

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["health"],
        summary="Service health check",
    )
    async def health() -> HealthResponse:
        """Lightweight liveness check — never requires Ollama to be running."""
        return HealthResponse(status="ok", service="extraction-copilot-backend")

    return app


app = create_app()
