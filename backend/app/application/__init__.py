"""Application layer.

Use cases orchestrate domain objects through port interfaces. This layer
depends ONLY on ``domain/`` — never on FastAPI, SQLAlchemy, or Ollama.
"""  # noqa: D401
