from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.artifacts import latest_phase_result
from axiom.phases import finish_task, run_design, run_execute, run_plan, run_review, run_verify
from axiom.task_file import create_task, load_task


class LifecycleFlowTest(unittest.TestCase):
    def test_finish_blocks_until_verify_and_review_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Lifecycle",
                kind="feature",
                now=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
            )

            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path, note="Applied code changes")

            blocked = finish_task(task_path)
            self.assertFalse(blocked.allowed)

            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[f"{sys.executable} -c \"print('still-ok')\""],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "CLI output looked correct"}],
            )
            run_review(task_path)
            allowed = finish_task(task_path)
            task = load_task(task_path)

        self.assertTrue(allowed.allowed)
        self.assertEqual(task.metadata.status, "done")

    def test_verify_records_command_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Verify",
                kind="feature",
                now=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path, note="Applied code changes")
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}],
            )
            task = load_task(task_path)
            verify_result = latest_phase_result(repo_root, task.metadata.id, "verify")

        self.assertEqual(task.metadata.status, "verify.passed")
        self.assertEqual(verify_result["outcome"], "passed")
        self.assertEqual(verify_result["automated_checks"][0]["status"], "passed")
