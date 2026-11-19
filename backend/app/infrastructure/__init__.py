"""Infrastructure layer.

Concrete adapters for external concerns (Ollama LLM, SQLite persistence) and
dependency-injection wiring. Adapters implement the domain ports in
``domain/ports.py``. This is the only layer where framework/vendor code lives.
"""  # noqa: D401
