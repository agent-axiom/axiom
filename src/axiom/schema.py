from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    pass


_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"

_FALLBACK_SCHEMAS: dict[str, dict[str, Any]] = {
    "plan": {
        "type": "object",
        "required": ["summary", "steps", "manual_smoke", "stop_conditions"],
        "properties": {
            "summary": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "title", "write_scope", "checks"],
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "write_scope": {"type": "array", "items": {"type": "string"}},
                        "checks": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "manual_smoke": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "instruction"],
                    "properties": {"id": {"type": "string"}, "instruction": {"type": "string"}},
                },
            },
            "stop_conditions": {"type": "array", "items": {"type": "string"}},
        },
    },
    "verify": {
        "type": "object",
        "required": ["outcome", "summary", "automated_checks", "negative_checks", "manual_smoke", "failures"],
        "properties": {
            "outcome": {"enum": ["passed", "failed", "blocked"]},
            "summary": {"type": "string"},
            "automated_checks": {"type": "array", "items": {"$ref": "#/$defs/commandReceipt"}},
            "negative_checks": {"type": "array", "items": {"$ref": "#/$defs/commandReceipt"}},
            "manual_smoke": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "status", "notes"],
                    "properties": {
                        "id": {"type": "string"},
                        "status": {"enum": ["passed", "failed", "waived"]},
                        "notes": {"type": "string"},
                    },
                },
            },
            "failures": {"type": "array", "items": {"type": "string"}},
        },
        "$defs": {
            "commandReceipt": {
                "type": "object",
                "required": ["name", "command", "status", "exit_code", "stdout", "stderr", "policy"],
                "properties": {
                    "name": {"type": "string"},
                    "command": {"type": "string"},
                    "status": {"enum": ["passed", "failed", "blocked"]},
                    "exit_code": {"type": "integer"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "policy": {"enum": ["allow", "deny", "escalate"]},
                    "policy_reason": {"type": "string"},
                },
            }
        },
    },
    "review": {
        "type": "object",
        "required": ["outcome", "summary", "findings", "next_phase"],
        "properties": {
            "outcome": {"enum": ["pass", "changes_requested", "blocked"]},
            "summary": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["severity", "title", "evidence"],
                    "properties": {
                        "severity": {"enum": ["blocker", "high", "medium", "low"]},
                        "title": {"type": "string"},
                        "file": {"type": "string"},
                        "line_start": {"type": "integer"},
                        "line_end": {"type": "integer"},
                        "evidence": {"type": "string"},
                        "required_fix": {"type": "string"},
                    },
                },
            },
            "next_phase": {"enum": ["execute", "plan", "design", "verify", "done"]},
        },
    },
}


def _load_schema(phase: str) -> dict[str, Any] | None:
    schema_path = _SCHEMA_ROOT / f"{phase}.schema.json"
    if schema_path.exists():
        return json.loads(schema_path.read_text(encoding="utf-8"))
    return _FALLBACK_SCHEMAS.get(phase)


def _resolve_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        raise SchemaValidationError(f"unsupported schema ref: {ref}")
    name = ref[len(prefix) :]
    try:
        return schema["$defs"][name]
    except KeyError as exc:
        raise SchemaValidationError(f"unknown schema ref: {ref}") from exc


def _check_type(path: str, expected_type: str, value: Any) -> None:
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "boolean": bool,
    }
    expected = type_map.get(expected_type)
    if expected is None:
        raise SchemaValidationError(f"{path}: unsupported schema type {expected_type}")
    if expected_type == "integer" and isinstance(value, bool):
        raise SchemaValidationError(f"{path}: expected integer")
    if not isinstance(value, expected):
        raise SchemaValidationError(f"{path}: expected {expected_type}")


def _validate_node(root_schema: dict[str, Any], node_schema: dict[str, Any], value: Any, path: str) -> None:
    if "$ref" in node_schema:
        _validate_node(root_schema, _resolve_ref(root_schema, str(node_schema["$ref"])), value, path)
        return

    if "enum" in node_schema and value not in node_schema["enum"]:
        raise SchemaValidationError(f"{path}: expected one of {node_schema['enum']}")

    expected_type = node_schema.get("type")
    if expected_type:
        _check_type(path, str(expected_type), value)

    if expected_type == "object":
        required = node_schema.get("required", [])
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}.{key}: missing required field")
        properties = node_schema.get("properties", {})
        for key, child_schema in properties.items():
            if key in value:
                _validate_node(root_schema, child_schema, value[key], f"{path}.{key}")

    if expected_type == "array":
        item_schema = node_schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_node(root_schema, item_schema, item, f"{path}[{index}]")


def validate_phase_payload(phase: str, payload: dict[str, object]) -> None:
    schema = _load_schema(phase)
    if schema is None:
        return
    _validate_node(schema, schema, payload, "$")
