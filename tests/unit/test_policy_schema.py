from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.artifacts import latest_phase_result
from axiom.approvals import approve_command
from axiom.phases import run_verify
from axiom.schema import SchemaValidationError, validate_phase_payload
from axiom.task_file import create_task, load_task


class PolicySchemaTest(unittest.TestCase):
    def test_validate_phase_payload_rejects_missing_required_fields(self) -> None:
        with self.assertRaises(SchemaValidationError):
            validate_phase_payload("plan", {"summary": "too small"})

    def test_verify_blocks_dangerous_git_command_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Policy gate",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_verify(
                task_path,
                commands=["git reset --hard"],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "policy smoke"}],
            )
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "verify")

        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["automated_checks"][0]["status"], "blocked")
        self.assertEqual(result["automated_checks"][0]["policy"], "deny")
        self.assertIn("destructive git operation", result["automated_checks"][0]["stderr"])

    def test_verify_escalates_dependency_changes_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Escalate dependency change",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_verify(
                task_path,
                commands=["pip install requests"],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "policy smoke"}],
            )
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "verify")

        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["automated_checks"][0]["status"], "blocked")
        self.assertEqual(result["automated_checks"][0]["policy"], "escalate")
        self.assertIn("dependency changes require explicit human approval", result["automated_checks"][0]["stderr"])

    def test_verify_runs_escalated_command_after_persisted_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Approved escalation",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            approval_id = approve_command(repo_root, "git push --dry-run", reason="test approval")
            run_verify(
                task_path,
                commands=["git push --dry-run"],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "policy smoke"}],
            )
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "verify")

        receipt = result["automated_checks"][0]
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["policy"], "escalate")
        self.assertEqual(receipt["approval_id"], approval_id)
        self.assertNotEqual(result["outcome"], "blocked")
