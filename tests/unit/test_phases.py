from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.artifacts import latest_phase_result
from axiom.phases import (
    PhaseTransitionError,
    finish_task,
    run_design,
    run_execute,
    run_plan,
    run_review,
    run_verify,
)
from axiom.task_file import create_task, load_task, update_task


class LifecycleFlowTest(unittest.TestCase):
    def test_phase_blocks_illegal_transition_and_records_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Illegal transition",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)

            with self.assertRaises(PhaseTransitionError):
                run_plan(task_path)
            task = load_task(task_path)
            decision = latest_phase_result(repo_root, task.metadata.id, "decision")

        self.assertEqual(task.metadata.status, "draft")
        self.assertEqual(decision["outcome"], "blocked")
        self.assertEqual(decision["phase"], "plan")
        self.assertEqual(decision["from_status"], "draft")
        self.assertEqual(decision["to_status"], "plan.passed")

    def test_force_allows_transition_and_records_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Forced transition",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )

            run_plan(task_path, force=True)
            task = load_task(task_path)
            decision = latest_phase_result(repo_root, task.metadata.id, "decision")

        self.assertEqual(task.metadata.status, "plan.passed")
        self.assertEqual(decision["outcome"], "forced")
        self.assertEqual(decision["phase"], "plan")
        self.assertEqual(decision["from_status"], "draft")
        self.assertEqual(decision["to_status"], "plan.passed")

    def test_successful_forced_phase_clears_stale_blocked_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Forced transition cleanup",
                kind="feature",
                now=datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
            )

            with self.assertRaises(PhaseTransitionError):
                run_plan(task_path)
            blocked = load_task(task_path)
            self.assertIn("plan transition blocked", blocked.metadata.blocked_reason)

            run_plan(task_path, force=True)
            task = load_task(task_path)
            decision = latest_phase_result(repo_root, task.metadata.id, "decision")

        self.assertEqual(task.metadata.status, "plan.passed")
        self.assertEqual(task.metadata.blocked_reason, "")
        self.assertEqual(decision["outcome"], "forced")

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
            update_task(
                task_path,
                section_updates={"Docs Impact": "No documentation changes required."},
                metadata_updates={"docs_status": "not_needed"},
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

    def test_verify_times_out_hung_command_and_records_failed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Timeout",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)

            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"import time; time.sleep(2)\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "timeout observed"}],
                timeout_seconds=0.1,
            )
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "verify")

        receipt = result["automated_checks"][0]
        self.assertEqual(task.metadata.status, "verify.failed")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["exit_code"], -1)
        self.assertIn("timed out after", receipt["stderr"])

    def test_verify_truncates_large_command_output_in_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Output cap",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)

            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('x' * 200)\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "output capped"}],
                max_output_chars=40,
            )
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "verify")

        stdout = result["automated_checks"][0]["stdout"]
        self.assertLessEqual(len(stdout), 40)
        self.assertIn("truncated", stdout)

    def test_plan_uses_repo_anchors_and_detected_make_test_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / "Makefile").write_text("test:\n\tpython3 -m unittest\n", encoding="utf-8")
            (repo_root / "src").mkdir()
            (repo_root / "tests").mkdir()
            task_path = create_task(
                repo_root=repo_root,
                title="Operational plan",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            update_task(
                task_path,
                section_updates={
                    "Repo Anchors": "- src/axiom/phases.py\n- tests/unit/test_phases.py",
                    "Scope": "Only change the phase runtime.",
                },
            )

            run_design(task_path)
            run_plan(task_path)
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "plan")

        write_scope = {item for step in result["steps"] for item in step["write_scope"]}
        checks = {item for step in result["steps"] for item in step["checks"]}
        self.assertIn("src/axiom/phases.py", write_scope)
        self.assertIn("tests/unit/test_phases.py", write_scope)
        self.assertIn("make test", checks)

    def test_review_requests_changes_when_verified_git_task_has_no_diff(self) -> None:
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
                title="Review no diff",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            update_task(
                task_path,
                section_updates={"Docs Impact": "No documentation changes required."},
                metadata_updates={"docs_status": "not_needed"},
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}],
            )

            run_review(task_path)
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(task.metadata.status, "review.changes_requested")
        self.assertEqual(result["outcome"], "changes_requested")
        self.assertTrue(any(finding["title"] == "No task-scoped diff found." for finding in result["findings"]))

    def test_review_passes_when_verified_git_task_has_diff_and_docs_disposition(self) -> None:
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
                title="Review with diff",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            update_task(
                task_path,
                section_updates={
                    "Repo Anchors": "- app.py",
                    "Docs Impact": "No documentation changes required.",
                },
                metadata_updates={"docs_status": "not_needed"},
            )
            run_design(task_path)
            run_plan(task_path)
            task = load_task(task_path)
            Path(task.metadata.worktree, "app.py").write_text("print('changed')\n", encoding="utf-8")
            run_execute(task_path)
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}],
            )

            run_review(task_path)
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(task.metadata.status, "review.passed")
        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(result["changed_files"], ["app.py"])
        self.assertEqual(result["planned_scope"], ["app.py"])
        self.assertEqual(result["actual_scope"], ["app.py"])
        self.assertEqual(result["scope_mismatches"], [])

    def test_review_requests_changes_when_actual_diff_escapes_plan_write_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            (repo_root / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py", "README.md"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
            task_path = create_task(
                repo_root=repo_root,
                title="Review scope",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            update_task(
                task_path,
                section_updates={
                    "Repo Anchors": "- app.py",
                    "Docs Impact": "No documentation changes required.",
                },
                metadata_updates={"docs_status": "not_needed"},
            )
            run_design(task_path)
            run_plan(task_path)
            task = load_task(task_path)
            Path(task.metadata.worktree, "README.md").write_text("changed outside scope\n", encoding="utf-8")
            run_execute(task_path)
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}],
            )

            run_review(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(result["outcome"], "changes_requested")
        self.assertTrue(any(finding["title"] == "Changed file outside plan write scope." for finding in result["findings"]))
        self.assertEqual(result["planned_scope"], ["app.py"])
        self.assertEqual(result["actual_scope"], ["README.md"])
        self.assertEqual(
            result["scope_mismatches"],
            [{"file": "README.md", "reason": "outside planned write scope"}],
        )

    def test_review_blocks_policy_config_changes_even_when_planned(self) -> None:
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
                title="Policy config edit",
                kind="feature",
                now=datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc),
            )
            update_task(
                task_path,
                section_updates={
                    "Repo Anchors": "- .axiom/policy.yaml",
                    "Docs Impact": "No documentation changes required.",
                },
                metadata_updates={"docs_status": "not_needed"},
            )
            run_design(task_path)
            run_plan(task_path)
            task = load_task(task_path)
            policy_path = Path(task.metadata.worktree, ".axiom", "policy.yaml")
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text("verify:\n  strict_allow:\n    - python3 -m unittest\n", encoding="utf-8")
            run_execute(task_path)
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}],
            )

            run_review(task_path)
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(task.metadata.status, "review.changes_requested")
        self.assertEqual(result["outcome"], "changes_requested")
        self.assertEqual(result["scope_mismatches"], [])
        self.assertTrue(any(finding["title"] == "Policy trust config changed." for finding in result["findings"]))

    def test_review_requests_changes_when_git_task_has_diff_but_no_plan_scope(self) -> None:
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
                title="Review missing plan",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            Path(task.metadata.worktree, "app.py").write_text("print('changed')\n", encoding="utf-8")
            update_task(
                task_path,
                section_updates={"Docs Impact": "No documentation changes required."},
                metadata_updates={"docs_status": "not_needed"},
            )
            run_design(task_path)
            run_execute(task_path, force=True)
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}],
            )

            run_review(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(result["outcome"], "changes_requested")
        self.assertEqual(result["planned_scope"], [])
        self.assertEqual(result["actual_scope"], ["app.py"])
        self.assertEqual(
            result["scope_mismatches"],
            [{"file": "app.py", "reason": "missing planned write scope"}],
        )

    def test_review_blocks_degraded_mode_without_manual_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Degraded review",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            update_task(
                task_path,
                section_updates={"Docs Impact": "No documentation changes required."},
                metadata_updates={"manual_smoke_required": False, "docs_status": "not_needed"},
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[],
            )

            run_review(task_path)
            task = load_task(task_path)
            result = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(task.metadata.isolation_mode, "degraded")
        self.assertEqual(result["outcome"], "changes_requested")
        self.assertTrue(
            any(finding["title"] == "Degraded isolation requires manual evidence." for finding in result["findings"])
        )

    def test_finish_respects_disabled_verification_and_review_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Optional gates",
                kind="chore",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            update_task(
                task_path,
                status="execute.passed",
                section_updates={"Docs Impact": "No documentation changes required."},
                metadata_updates={
                    "verification_required": False,
                    "review_required": False,
                    "manual_smoke_required": False,
                    "docs_status": "not_needed",
                },
            )

            decision = finish_task(task_path)
            task = load_task(task_path)

        self.assertTrue(decision.allowed)
        self.assertEqual(task.metadata.status, "done")

    def test_finish_can_skip_review_when_review_required_is_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="No review gate",
                kind="chore",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            run_plan(task_path)
            run_execute(task_path)
            run_verify(
                task_path,
                commands=[f"{sys.executable} -c \"print('ok')\""],
                negative_commands=[],
                manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}],
            )
            update_task(
                task_path,
                section_updates={"Docs Impact": "No documentation changes required."},
                metadata_updates={"review_required": False, "docs_status": "not_needed"},
            )

            decision = finish_task(task_path)
            task = load_task(task_path)

        self.assertTrue(decision.allowed)
        self.assertEqual(task.metadata.status, "done")
