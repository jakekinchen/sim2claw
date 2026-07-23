"""JSON-schema validation for autonomous development-loop artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "configs" / "dev_loop" / "schemas"
SCHEMA_PATHS = {
    "task": SCHEMA_ROOT / "task_contract_v1.json",
    "review": SCHEMA_ROOT / "review_receipt_v1.json",
    "test": SCHEMA_ROOT / "test_receipt_v1.json",
    "process": SCHEMA_ROOT / "process_lease_v1.json",
    "merge": SCHEMA_ROOT / "merge_readiness_v1.json",
}


class DevLoopContractError(ValueError):
    """A development-loop artifact failed its frozen JSON schema."""


def load_dev_loop_schema(name: str) -> dict[str, Any]:
    try:
        path = SCHEMA_PATHS[name]
    except KeyError as error:
        raise DevLoopContractError(f"unknown development-loop schema: {name}") from error
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(value)
    except (OSError, json.JSONDecodeError, SchemaError) as error:
        raise DevLoopContractError(f"invalid development-loop schema {path}: {error}") from error
    return value


def validate_dev_loop_artifact(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    try:
        Draft202012Validator(
            load_dev_loop_schema(name),
            format_checker=FormatChecker(),
        ).validate(normalized)
    except ValidationError as error:
        path = ".".join(str(value) for value in error.absolute_path) or "<root>"
        raise DevLoopContractError(
            f"development-loop {name} schema violation at {path}: {error.message}"
        ) from error
    return normalized


__all__ = [
    "DevLoopContractError",
    "REPO_ROOT",
    "SCHEMA_PATHS",
    "load_dev_loop_schema",
    "validate_dev_loop_artifact",
]
