from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.adapters import build_adapter_request
from axiom.artifacts import latest_phase_result
from axiom.phases import run_design, run_execute, run_plan
from axiom.schema import validate_phase_payload
from axiom.task_file import create_task, load_task, update_task


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")


def _init_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "axiom@example.test")
    _git(repo_root, "config", "user.name", "AXIOM Test")
    (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
    _git(repo_root, "add", "app.py")
    _git(repo_root, "commit", "-m", "initial")


class AdapterTest(unittest.TestCase):
    def test_adapter_protocol_spec_and_reference_adapters_are_present(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        spec_path = repo_root / "docs" / "ADAPTER_PROTOCOL.md"
        request_schema_path = repo_root / "schemas" / "adapter-request.schema.json"
        static_plan = repo_root / "examples" / "adapters" / "static_plan_adapter.py"
        file_writer = repo_root / "examples" / "adapters" / "file_write_execute_adapter.py"
        openai_compatible = repo_root / "examples" / "adapters" / "openai_compatible_plan_adapter.py"

        request_schema = json.loads(request_schema_path.read_text(encoding="utf-8"))

        self.assertTrue(spec_path.exists())
        self.assertEqual(request_schema["properties"]["protocol"]["const"], "axiom.adapter.v1")
        self.assertEqual(request_schema["properties"]["phase"]["enum"], ["plan", "execute"])
        self.assertTrue(static_plan.exists())
        self.assertTrue(file_writer.exists())
        self.assertTrue(openai_compatible.exists())

    def test_build_adapter_request_includes_task_workspace_and_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Adapter request",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            update_task(task_path, section_updates={"Objective": "Use adapter."})
            task = load_task(task_path)

            request = build_adapter_request(phase="plan", task=task, task_path=task_path)
            validate_phase_payload("adapter-request", request)

        self.assertEqual(request["protocol"], "axiom.adapter.v1")
        self.assertEqual(request["phase"], "plan")
        self.assertEqual(request["task"]["id"], "AX-20260424-001")
        self.assertEqual(request["workspace"], task.metadata.worktree)
        self.assertEqual(request["base_commit"], task.metadata.base_commit)
        self.assertEqual(request["isolation_mode"], task.metadata.isolation_mode)
        self.assertEqual(request["sections"]["Objective"], "Use adapter.")

    def test_plan_can_use_command_adapter_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            adapter_script = repo_root / "plan_adapter.py"
            adapter_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys

                    request = json.load(sys.stdin)
                    json.dump({
                        "summary": "Adapter plan for " + request["task"]["title"],
                        "steps": [
                            {
                                "id": "step-1",
                                "title": "Edit app.py through the adapter plan.",
                                "write_scope": ["app.py"],
                                "checks": ["python3 -m unittest discover -s tests -v"]
                            }
                        ],
                        "manual_smoke": [
                            {"id": "smoke-1", "instruction": "Run app.py manually."}
                        ],
                        "stop_conditions": ["Stop on files outside app.py."]
                    }, sys.stdout)
                    """
                ).strip(),
                encoding="utf-8",
            )
            task_path = create_task(
                repo_root=repo_root,
                title="Adapter plan",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )

            run_design(task_path)
            run_plan(task_path, adapter_command=f"{sys.executable} {adapter_script}")
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "plan")

        self.assertEqual(result["summary"], "Adapter plan for Adapter plan")
        self.assertEqual(result["steps"][0]["write_scope"], ["app.py"])
        self.assertEqual(result["adapter"]["status"], "passed")

    def test_execute_command_adapter_can_modify_task_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)
            adapter_script = repo_root / "execute_adapter.py"
            adapter_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import pathlib
                    import sys

                    request = json.load(sys.stdin)
                    pathlib.Path(request["workspace"], "app.py").write_text("print('adapter changed')\\n")
                    json.dump({"summary": "Adapter modified app.py"}, sys.stdout)
                    """
                ).strip(),
                encoding="utf-8",
            )
            task_path = create_task(
                repo_root=repo_root,
                title="Adapter execute",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )

            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path, adapter_command=f"{sys.executable} {adapter_script}")
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "execute")

        self.assertEqual(result["summary"], "Adapter modified app.py")
        self.assertEqual(result["changed_files"], ["app.py"])
        self.assertEqual(result["new_changed_files"], ["app.py"])
        self.assertEqual(result["adapter"]["status"], "passed")

    def test_plan_adapter_invalid_json_is_persisted_as_blocked_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            adapter_script = repo_root / "bad_adapter.py"
            adapter_script.write_text("print('not json')\n", encoding="utf-8")
            task_path = create_task(
                repo_root=repo_root,
                title="Bad adapter",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)

            run_plan(task_path, adapter_command=f"{sys.executable} {adapter_script}")
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "plan")

        self.assertEqual(task.metadata.status, "plan.blocked")
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["adapter"]["status"], "failed")
        self.assertIn("valid JSON", result["failures"][0])

    def test_plan_adapter_schema_failure_is_persisted_as_blocked_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            adapter_script = repo_root / "bad_schema_adapter.py"
            adapter_script.write_text(
                "import json, sys\njson.dump({'summary': 'missing required plan fields'}, sys.stdout)\n",
                encoding="utf-8",
            )
            task_path = create_task(
                repo_root=repo_root,
                title="Bad adapter schema",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)

            run_plan(task_path, adapter_command=f"{sys.executable} {adapter_script}")
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "plan")

        self.assertEqual(task.metadata.status, "plan.blocked")
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["adapter"]["status"], "passed")
        self.assertIn("schema validation", result["failures"][0])

    def test_adapter_allowlist_blocks_unapproved_local_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            adapter_script = repo_root / "plan_adapter.py"
            adapter_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys

                    json.dump({
                        "summary": "Should be blocked",
                        "steps": [],
                        "manual_smoke": [],
                        "stop_conditions": []
                    }, sys.stdout)
                    """
                ).strip(),
                encoding="utf-8",
            )
            task_path = create_task(
                repo_root=repo_root,
                title="Adapter trust",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            old_allowlist = os.environ.get("AXIOM_ADAPTER_ALLOWLIST")
            os.environ["AXIOM_ADAPTER_ALLOWLIST"] = str((repo_root / "other_adapter.py").resolve())
            try:
                run_plan(task_path, adapter_command=f"{sys.executable} {adapter_script}")
            finally:
                if old_allowlist is None:
                    os.environ.pop("AXIOM_ADAPTER_ALLOWLIST", None)
                else:
                    os.environ["AXIOM_ADAPTER_ALLOWLIST"] = old_allowlist
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "plan")

        self.assertEqual(task.metadata.status, "plan.blocked")
        self.assertEqual(result["adapter"]["status"], "blocked")
        self.assertIn("AXIOM_ADAPTER_ALLOWLIST", result["adapter"]["stderr"])
