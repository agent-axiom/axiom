from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.artifacts import latest_phase_result
from axiom.approvals import approve_command
from axiom.phases import run_design, run_execute, run_plan, run_verify
from axiom.policy import evaluate_command
from axiom.schema import SchemaValidationError, unsupported_schema_keywords, validate_schema_subset, validate_phase_payload
from axiom.task_file import create_task, load_task


class PolicySchemaTest(unittest.TestCase):
    def test_validate_phase_payload_rejects_missing_required_fields(self) -> None:
        with self.assertRaises(SchemaValidationError):
            validate_phase_payload("plan", {"summary": "too small"})

    def test_all_persisted_phase_schemas_are_present_and_enforced(self) -> None:
        validate_phase_payload("design", {"summary": "ok", "repo_anchors": []})
        validate_phase_payload(
            "execute",
            {
                "summary": "ok",
                "changed_files": [],
                "pre_changed_files": [],
                "new_changed_files": [],
            },
        )
        validate_phase_payload("finish", {"outcome": "blocked", "summary": "not ready"})
        with self.assertRaises(SchemaValidationError):
            validate_phase_payload("adapter-request", {"protocol": "wrong"})

    def test_schema_subset_rejects_unsupported_keywords_instead_of_ignoring_them(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"summary": {"type": "string"}},
        }

        self.assertEqual(unsupported_schema_keywords(schema), ["$.additionalProperties"])
        with self.assertRaisesRegex(SchemaValidationError, "unsupported schema keyword"):
            validate_schema_subset(schema)

    def test_verify_blocks_dangerous_git_command_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Policy gate",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)
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
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)
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

    def test_strict_policy_blocks_ad_hoc_python_command(self) -> None:
        decision = evaluate_command(f"{sys.executable} -c \"print('ok')\"", profile="strict")

        self.assertEqual(decision.action, "deny")
        self.assertIn("strict policy", decision.reason)

    def test_strict_policy_allows_explicit_command_allowlist(self) -> None:
        command = f"{sys.executable} -c \"print('ok')\""
        decision = evaluate_command(command, profile="strict", command_allowlist=[command])

        self.assertEqual(decision.action, "allow")

    def test_strict_policy_allows_known_test_runner(self) -> None:
        decision = evaluate_command(f"{sys.executable} -m unittest discover -s tests/unit -v", profile="strict")

        self.assertEqual(decision.action, "allow")

    def test_permissive_policy_still_denies_destructive_commands(self) -> None:
        decision = evaluate_command("rm -rf important", profile="permissive")

        self.assertEqual(decision.action, "deny")

    def test_verify_runs_escalated_command_after_persisted_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
            task_path = create_task(
                repo_root=repo_root,
                title="Approved escalation",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)
            task = load_task(task_path)
            run_verify(
                task_path,
                commands=["git push --dry-run"],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "policy smoke"}],
            )
            blocked = latest_phase_result(repo_root, task.metadata.id, "verify")
            approval_id = approve_command(
                repo_root,
                "git push --dry-run",
                reason="test approval",
                task_id=task.metadata.id,
                worktree=task.metadata.worktree,
            )
            run_verify(
                task_path,
                commands=["git push --dry-run"],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "policy smoke"}],
            )
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "verify")

        self.assertEqual(blocked["outcome"], "blocked")
        self.assertEqual(blocked["automated_checks"][0]["exit_code"], -1)
        receipt = result["automated_checks"][0]
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["policy"], "escalate")
        self.assertEqual(receipt["approval_id"], approval_id)
        self.assertEqual(receipt["approval_reason"], "test approval")
        self.assertEqual(
            receipt["approval_scope"],
            {
                "repo_root": str(repo_root.resolve()),
                "task_id": task.metadata.id,
                "worktree": task.metadata.worktree,
            },
        )
        self.assertNotEqual(receipt["exit_code"], -1)
        self.assertNotEqual(result["outcome"], "blocked")
