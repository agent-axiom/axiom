from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    pass


_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"

_FALLBACK_SCHEMAS: dict[str, dict[str, Any]] = {
    "adapter-request": {
        "type": "object",
        "required": [
            "protocol",
            "phase",
            "task",
            "task_path",
            "repo_root",
            "workspace",
            "base_branch",
            "base_commit",
            "branch",
            "isolation_mode",
            "sections",
            "latest_artifacts",
            "diff",
        ],
        "properties": {
            "protocol": {"const": "axiom.adapter.v1"},
            "phase": {"enum": ["plan", "execute"]},
            "task": {
                "type": "object",
                "required": ["id", "title", "kind", "status", "risk"],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "kind": {"type": "string"},
                    "status": {"type": "string"},
                    "risk": {"type": "string"},
                },
            },
            "task_path": {"type": "string"},
            "repo_root": {"type": "string"},
            "workspace": {"type": "string"},
            "base_branch": {"type": "string"},
            "base_commit": {"type": "string"},
            "branch": {"type": "string"},
            "isolation_mode": {"enum": ["worktree", "degraded"]},
            "sections": {"type": "object"},
            "latest_artifacts": {"type": "object"},
            "diff": {"type": "string"},
        },
    },
    "design": {
        "type": "object",
        "required": ["summary", "repo_anchors"],
        "properties": {
            "summary": {"type": "string"},
            "repo_anchors": {"type": "array", "items": {"type": "string"}},
        },
    },
    "execute": {
        "type": "object",
        "required": ["summary", "changed_files", "pre_changed_files", "new_changed_files"],
        "properties": {
            "outcome": {"enum": ["passed", "failed", "blocked"]},
            "summary": {"type": "string"},
            "changed_files": {"type": "array", "items": {"type": "string"}},
            "pre_changed_files": {"type": "array", "items": {"type": "string"}},
            "new_changed_files": {"type": "array", "items": {"type": "string"}},
            "failures": {"type": "array", "items": {"type": "string"}},
            "adapter": {"type": "object"},
        },
    },
    "finish": {
        "type": "object",
        "required": ["outcome", "summary"],
        "properties": {
            "outcome": {"enum": ["passed", "blocked"]},
            "summary": {"type": "string"},
        },
    },
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
                    "approval_id": {"type": "string"},
                    "approval_reason": {"type": "string"},
                    "approval_scope": {"type": "object"},
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


def _load_packaged_schema(phase: str) -> dict[str, Any] | None:
    try:
        schema_path = resources.files("axiom").joinpath("schemas", f"{phase}.schema.json")
        if schema_path.is_file():
            return json.loads(schema_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError):
        return None
    return None


def _load_schema(phase: str) -> dict[str, Any] | None:
    packaged_schema = _load_packaged_schema(phase)
    if packaged_schema is not None:
        return packaged_schema
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

    if "const" in node_schema and value != node_schema["const"]:
        raise SchemaValidationError(f"{path}: expected {node_schema['const']!r}")

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
