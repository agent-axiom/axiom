from __future__ import annotations

import json
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
from axiom.phases import run_execute, run_plan
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

        request_schema = json.loads(request_schema_path.read_text(encoding="utf-8"))

        self.assertTrue(spec_path.exists())
        self.assertEqual(request_schema["properties"]["protocol"]["const"], "axiom.adapter.v1")
        self.assertTrue(static_plan.exists())
        self.assertTrue(file_writer.exists())

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

        self.assertEqual(request["protocol"], "axiom.adapter.v1")
        self.assertEqual(request["phase"], "plan")
        self.assertEqual(request["task"]["id"], "AX-20260424-001")
        self.assertEqual(request["workspace"], task.metadata.worktree)
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

            run_execute(task_path, adapter_command=f"{sys.executable} {adapter_script}")
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "execute")

        self.assertEqual(result["summary"], "Adapter modified app.py")
        self.assertEqual(result["changed_files"], ["app.py"])
        self.assertEqual(result["new_changed_files"], ["app.py"])
        self.assertEqual(result["adapter"]["status"], "passed")
