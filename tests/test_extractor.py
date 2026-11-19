"""Tests for the resilient JSON extractor/validator (fully offline)."""

from __future__ import annotations

import pytest

from infrastructure.extractor import (
    clean_llm_response,
    extract_and_validate,
    strip_markdown_fences,
    strip_think_tags,
)


SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "entities": {"type": "array", "items": {"type": "string"}},
        "count": {"type": "integer"},
    },
    "required": ["summary"],
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<think>reasoning here</think>{\"a\": 1}", '{"a": 1}'),
        ("<think>line1\nline2</think>\n{\"a\": 1}", '{"a": 1}'),
        ("plain output", "plain output"),
        ("<think>unclosed reasoning", ""),
    ],
)
def test_strip_think_tags(raw: str, expected: str) -> None:
    assert strip_think_tags(raw).strip() == expected


def test_strip_markdown_fences() -> None:
    raw = '```json\n{"summary": "ok"}\n```'
    assert strip_markdown_fences(raw).strip() == '{"summary": "ok"}'
    assert strip_markdown_fences("no fences").strip() == "no fences"


def test_clean_llm_response_handles_think_and_fence() -> None:
    raw = (
        "<think>Let me think about this step by step...</think>\n"
        "```json\n"
        '{"summary": "ok", "entities": []}\n'
        "```"
    )
    cleaned = clean_llm_response(raw)
    assert "<think>" not in cleaned
    assert "```" not in cleaned
    assert cleaned.startswith("{")


def test_extract_valid_json_no_retries() -> None:
    payload, success, diagnostic, retries = extract_and_validate(
        '{"summary": "ok", "count": 3}', SCHEMA, max_retries=2
    )
    assert success is True
    assert payload == {"summary": "ok", "count": 3}
    assert diagnostic == ""
    assert retries == 0


def test_extract_with_think_fence_and_prose() -> None:
    raw = (
        "<think>hidden</think>\n"
        "Here is the result:\n"
        '```json\n{"summary": "ok"}\n```\n'
        "Hope that helps."
    )
    payload, success, _, retries = extract_and_validate(raw, SCHEMA, max_retries=2)
    assert success is True
    assert payload == {"summary": "ok"}
    # The surrounding prose requires one brace-balancing repair attempt.
    assert retries == 1


def test_repair_trailing_comma_with_bounded_retries() -> None:
    raw = '{"summary": "ok", "entities": ["a", "b",],}'
    payload, success, diagnostic, retries = extract_and_validate(
        raw, SCHEMA, max_retries=2
    )
    assert success is True
    assert payload == {"summary": "ok", "entities": ["a", "b"]}
    assert retries <= 2


def test_schema_invalid_fields_return_diagnostic_and_partial_payload() -> None:
    raw = '{"summary": 42, "entities": "not-a-list"}'
    payload, success, diagnostic, retries = extract_and_validate(
        raw, SCHEMA, max_retries=2
    )
    assert success is False
    assert payload == {"summary": 42, "entities": "not-a-list"}
    assert "schema validation failed" in diagnostic
    assert "summary" in diagnostic
    assert retries > 0


def test_missing_required_field_is_reported() -> None:
    payload, success, diagnostic, _ = extract_and_validate(
        '{"entities": ["x"]}', SCHEMA, max_retries=1
    )
    assert success is False
    assert payload == {"entities": ["x"]}
    assert "missing required field 'summary'" in diagnostic


def test_unparseable_input_is_cleanly_rejected() -> None:
    payload, success, diagnostic, retries = extract_and_validate(
        "<think>nope</think> not json at all", SCHEMA, max_retries=2
    )
    assert success is False
    assert payload is None
    assert "unparseable JSON" in diagnostic
    assert retries == 3  # initial attempt + 2 bounded retries


def test_retry_count_never_exceeds_budget() -> None:
    for max_retries in (0, 1, 2, 5):
        _, success, _, retries = extract_and_validate(
            "garbage", SCHEMA, max_retries=max_retries
        )
        assert not success
        assert retries <= max_retries + 1


def test_braces_inside_strings_are_handled() -> None:
    raw = 'prefix {"summary": "uses {braces} inside", "count": 1} suffix'
    payload, success, _, _ = extract_and_validate(raw, SCHEMA, max_retries=2)
    assert success is True
    assert payload == {"summary": "uses {braces} inside", "count": 1}


def test_python_literal_fallback() -> None:
    raw = "{'summary': 'single quotes', 'count': 2}"
    payload, success, _, _ = extract_and_validate(raw, SCHEMA, max_retries=2)
    assert success is True
    assert payload == {"summary": "single quotes", "count": 2}
