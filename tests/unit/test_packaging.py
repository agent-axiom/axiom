from __future__ import annotations

import importlib.resources
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import axiom.schema as schema_module
from axiom.schema import SchemaValidationError, validate_phase_payload


class PackagingTest(unittest.TestCase):
    def test_schema_resources_are_packaged_inside_axiom(self) -> None:
        schema_root = importlib.resources.files("axiom").joinpath("schemas")
        self.assertTrue(schema_root.joinpath("adapter-request.schema.json").is_file())
        self.assertTrue(schema_root.joinpath("plan.schema.json").is_file())

    def test_packaged_schemas_match_repo_contract_schemas(self) -> None:
        repo_schema_root = Path(__file__).resolve().parents[2] / "schemas"
        package_schema_root = importlib.resources.files("axiom").joinpath("schemas")
        for repo_schema in repo_schema_root.glob("*.schema.json"):
            package_schema = package_schema_root.joinpath(repo_schema.name)
            self.assertTrue(package_schema.is_file(), repo_schema.name)
            self.assertEqual(
                json.loads(package_schema.read_text(encoding="utf-8")),
                json.loads(repo_schema.read_text(encoding="utf-8")),
                repo_schema.name,
            )

    def test_adapter_request_schema_is_enforced_without_repo_schema_files(self) -> None:
        original_root = schema_module._SCHEMA_ROOT
        schema_module._SCHEMA_ROOT = Path("/definitely/missing/axiom/schemas")
        try:
            with self.assertRaises(SchemaValidationError):
                validate_phase_payload(
                    "adapter-request",
                    {
                        "protocol": "wrong",
                        "phase": "review",
                        "task": {},
                        "task_path": "",
                        "repo_root": "",
                        "workspace": "",
                        "base_branch": "",
                        "base_commit": "",
                        "branch": "",
                        "isolation_mode": "worktree",
                        "sections": {},
                        "latest_artifacts": {},
                        "diff": "",
                    },
                )
        finally:
            schema_module._SCHEMA_ROOT = original_root
