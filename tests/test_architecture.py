"""Guardrails enforcing the Clean Architecture dependency rules."""

from __future__ import annotations

import re
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)", re.MULTILINE)


def _imported_modules(layer: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for path in (_APP_ROOT / layer).glob("*.py"):
        roots = {match.split(".")[0] for match in _IMPORT_RE.findall(path.read_text())}
        result[path.name] = roots
    return result


def test_domain_has_no_framework_or_vendor_imports() -> None:
    banned = {"fastapi", "starlette", "httpx", "sqlite3", "sqlalchemy", "infrastructure", "presentation", "application"}
    for filename, roots in _imported_modules("domain").items():
        assert not (roots & banned), f"{filename} imports forbidden modules: {roots & banned}"


def test_application_depends_only_on_domain_and_stdlib() -> None:
    banned = {
        "fastapi",
        "starlette",
        "httpx",
        "sqlite3",
        "sqlalchemy",
        "infrastructure",
        "presentation",
    }
    for filename, roots in _imported_modules("application").items():
        assert not (roots & banned), f"{filename} imports forbidden modules: {roots & banned}"
        if filename != "__init__.py":
            assert "domain" in roots, f"{filename} does not use the domain layer"
