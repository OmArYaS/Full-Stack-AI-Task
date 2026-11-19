"""Resilient structured JSON extractor / validator.

Pure standard-library utilities for turning raw local-model output into a
schema-validated Python object:

1. Strip ``<think>...</think>`` reasoning tags (including unclosed tags).
2. Strip markdown code fences (```` ```json ... ``` ````).
3. Parse JSON with bounded repair strategies (trailing commas, brace
   balancing, Python-literal fallback).
4. Validate the parsed payload against a simple JSON Schema subset.

All functions are deterministic and side-effect free so they can be tested
offline without any LLM running.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from domain.ports import ParsedOutput

# Reasoning tags emitted by some local models (e.g. deepseek-r1).
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*", re.IGNORECASE | re.DOTALL)

# Markdown code fences, optionally language-tagged.
_FENCE_RE = re.compile(r"```(?:\w+)?\s*\n(.*?)```", re.DOTALL)
_STRAY_FENCE_RE = re.compile(r"```")

# Trailing commas before closing brackets/braces.
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


class ExtractionParseError(Exception):
    """Raised when JSON cannot be repaired within the retry budget."""


def strip_think_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks, including unclosed ones."""
    text = _THINK_TAG_RE.sub("", text)
    text = _UNCLOSED_THINK_RE.sub("", text)
    return text


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences while keeping the fenced content."""
    text = _FENCE_RE.sub(lambda match: match.group(1), text)
    text = _STRAY_FENCE_RE.sub("", text)
    return text


def clean_llm_response(text: str) -> str:
    """Strip reasoning tags and fences, returning the candidate JSON text."""
    return strip_markdown_fences(strip_think_tags(text)).strip()


def _scan_balanced_braces(text: str, start: int) -> str | None:
    """Extract the substring from ``start`` to its matching closing brace.

    Handles double-quoted strings with escapes so braces inside strings are
    ignored. Returns ``None`` when braces never balance.
    """
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if in_string:
            if char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _extract_candidate(text: str) -> str:
    """Pick the best JSON candidate from cleaned text."""
    stripped = text.strip()
    # 1. Try the whole string.
    return stripped


def _balance_braces_candidate(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    return _scan_balanced_braces(text, start)


def _remove_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _braces_then_trailing_commas(text: str) -> str | None:
    balanced = _balance_braces_candidate(text)
    if balanced is None:
        return None
    return _remove_trailing_commas(balanced)


def _try_parse(text: str) -> Any:
    """Parse JSON, falling back to Python literal evaluation."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some models emit Python-ish literals with single quotes.
        return ast.literal_eval(text)


def _validate_against_schema(payload: Any, schema: dict[str, Any]) -> list[str]:
    """Validate payload against a small JSON Schema subset.

    Supports: type (object/array/string/number/integer/boolean), required,
    properties, and items. Returns a list of human-readable error messages.
    """
    errors: list[str] = []

    def check(value: Any, sub_schema: dict[str, Any], path: str) -> None:
        expected_type = sub_schema.get("type")
        if expected_type is None:
            return
        type_ok = {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        }.get(expected_type, True)
        if not type_ok:
            errors.append(f"{path or 'root'}: expected {expected_type}")
            return
        if expected_type == "object" and isinstance(value, dict):
            for key in sub_schema.get("required", []):
                if key not in value:
                    errors.append(f"{path or 'root'}: missing required field '{key}'")
            for key, prop_schema in sub_schema.get("properties", {}).items():
                if key in value:
                    check(value[key], prop_schema, f"{path}.{key}" if path else key)
        if expected_type == "array" and isinstance(value, list):
            item_schema = sub_schema.get("items")
            if item_schema is not None:
                for index, item in enumerate(value):
                    check(item, item_schema, f"{path}[{index}]" if path else f"[{index}]")

    check(payload, schema, "")
    return errors


def extract_and_validate(
    raw_response: str,
    schema: dict[str, Any],
    *,
    max_retries: int = 2,
) -> tuple[dict[str, Any] | None, bool, str, int]:
    """Parse and validate raw LLM output with bounded repair retries.

    Returns ``(payload, success, diagnostic, retry_count)``.

    * ``payload`` is the parsed dict (or ``None`` when unparseable).
    * ``success`` is True only when parsing AND schema validation passed.
    * ``diagnostic`` describes the failure when ``success`` is False.
    * ``retry_count`` is the number of failed parse/validate attempts.
    """
    cleaned = clean_llm_response(raw_response)
    # Each strategy progressively repairs the cleaned text. The number of
    # attempts is bounded by max_retries + 1 (the initial parse plus retries).
    strategies = [
        lambda text: text,  # attempt 0: cleaned response as-is
        _balance_braces_candidate,  # trim prose around the JSON object
        _remove_trailing_commas,  # fix a common small-model mistake
        _braces_then_trailing_commas,  # both fixes together
    ]

    retry_count = 0
    last_error = ""
    best_payload: dict[str, Any] | None = None

    for attempt in range(max_retries + 1):
        strategy = strategies[min(attempt, len(strategies) - 1)]
        candidate = strategy(cleaned)
        if candidate is None or not candidate.strip():
            candidate = cleaned

        try:
            parsed = _try_parse(candidate)
        except Exception as exc:  # noqa: BLE001 - capture any parse failure
            last_error = f"unparseable JSON: {exc}"
            retry_count += 1
            continue

        if not isinstance(parsed, dict):
            last_error = f"parsed value is not a JSON object: {type(parsed).__name__}"
            retry_count += 1
            continue

        # Remember the best-effort payload so callers can offer manual fixes.
        if best_payload is None:
            best_payload = parsed

        validation_errors = _validate_against_schema(parsed, schema)
        if validation_errors:
            last_error = "schema validation failed: " + "; ".join(validation_errors)
            retry_count += 1
            # A later repair strategy might still produce a valid payload.
            continue

        return parsed, True, "", retry_count

    diagnostic = last_error or "extraction failed after repair attempts"
    return best_payload, False, diagnostic, retry_count


class ResilientJsonParser:
    """Adapter implementing the domain ``StructuredOutputParser`` port."""

    def parse(
        self, raw_response: str, schema: dict[str, Any], *, max_retries: int = 2
    ) -> ParsedOutput:
        """Parse raw LLM output with think/fence stripping and bounded repair."""
        return extract_and_validate(raw_response, schema, max_retries=max_retries)
