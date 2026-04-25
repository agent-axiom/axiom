from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.cli import main
from axiom.artifacts import latest_phase_result
from axiom.task_file import load_task, update_task


def _run_cli(argv: list[str]) -> int:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        return main(argv)


class CommandIntegrationTest(unittest.TestCase):
    def test_make_and_show_commands_run_without_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "make", "Bootstrap task"])
            output = stdout.getvalue().strip()

            self.assertEqual(exit_code, 0)
            self.assertIn(".axiom/tasks", output)

            task_path = Path(output)
            show_stdout = io.StringIO()
            with redirect_stdout(show_stdout):
                show_code = main(["--repo-root", str(repo_root), "show", task_path.name])

        self.assertEqual(show_code, 0)
        self.assertIn("Bootstrap task", show_stdout.getvalue())

    def test_doctor_json_reports_environment_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "doctor", "--json"])

        payload = json.loads(stdout.getvalue())
        checks = {item["name"]: item for item in payload["checks"]}
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["overall"], "pass")
        self.assertEqual(checks["schema availability"]["status"], "pass")
        self.assertEqual(checks["git head"]["status"], "pass")
        self.assertEqual(checks["worktree readiness"]["status"], "pass")
        self.assertIn(payload["runtime_mode"], {"source", "installed"})

    def test_doctor_warns_for_non_git_repo_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "doctor", "--json"])

        payload = json.loads(stdout.getvalue())
        checks = {item["name"]: item for item in payload["checks"]}
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["overall"], "warn")
        self.assertEqual(checks["git repository"]["status"], "warn")
        self.assertEqual(checks["worktree readiness"]["status"], "warn")

    def test_worktree_list_and_path_commands_use_task_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--repo-root", str(repo_root), "make", "Worktree UX"]), 0)
            task_path = Path(stdout.getvalue().strip())
            task = load_task(task_path)

            list_stdout = io.StringIO()
            with redirect_stdout(list_stdout):
                list_code = main(["--repo-root", str(repo_root), "worktree", "list"])
            path_stdout = io.StringIO()
            with redirect_stdout(path_stdout):
                path_code = main(["--repo-root", str(repo_root), "worktree", "path", str(task_path)])

        self.assertEqual(list_code, 0)
        self.assertEqual(path_code, 0)
        self.assertIn(task.metadata.id, list_stdout.getvalue())
        self.assertIn(task.metadata.isolation_mode, list_stdout.getvalue())
        self.assertEqual(path_stdout.getvalue().strip(), task.metadata.worktree)

    def test_cleanup_dry_run_only_if_done_and_default_branch_keep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--repo-root", str(repo_root), "make", "Cleanup UX"]), 0)
            task_path = Path(stdout.getvalue().strip())
            task = load_task(task_path)
            worktree = Path(task.metadata.worktree)

            dry_run_stdout = io.StringIO()
            with redirect_stdout(dry_run_stdout):
                dry_run_code = main(["--repo-root", str(repo_root), "cleanup", str(task_path), "--dry-run"])
            worktree_exists_after_dry_run = worktree.exists()

            only_done_stdout = io.StringIO()
            with redirect_stdout(only_done_stdout):
                only_done_code = main(["--repo-root", str(repo_root), "cleanup", str(task_path), "--only-if-done"])
            worktree_exists_after_only_done = worktree.exists()

            cleanup_stdout = io.StringIO()
            with redirect_stdout(cleanup_stdout):
                cleanup_code = main(["--repo-root", str(repo_root), "cleanup", str(task_path), "--force"])
            branch_check = subprocess.run(
                ["git", "show-ref", "--verify", f"refs/heads/{task.metadata.branch}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(dry_run_code, 0)
        self.assertIn("would remove worktree", dry_run_stdout.getvalue())
        self.assertIn("would keep branch", dry_run_stdout.getvalue())
        self.assertTrue(worktree_exists_after_dry_run)
        self.assertEqual(only_done_code, 1)
        self.assertIn("task is not done", only_done_stdout.getvalue())
        self.assertTrue(worktree_exists_after_only_done)
        self.assertEqual(cleanup_code, 0)
        self.assertIn("worktree removed", cleanup_stdout.getvalue())
        self.assertIn("branch kept", cleanup_stdout.getvalue())
        self.assertFalse(worktree.exists())
        self.assertEqual(branch_check.returncode, 0)

    def test_cleanup_can_delete_branch_after_done_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--repo-root", str(repo_root), "make", "Cleanup branch"]), 0)
            task_path = Path(stdout.getvalue().strip())
            update_task(task_path, status="done")
            task = load_task(task_path)
            worktree = Path(task.metadata.worktree)

            cleanup_stdout = io.StringIO()
            with redirect_stdout(cleanup_stdout):
                cleanup_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "cleanup",
                        str(task_path),
                        "--only-if-done",
                        "--force",
                        "--delete-branch",
                    ]
                )
            branch_check = subprocess.run(
                ["git", "show-ref", "--verify", f"refs/heads/{task.metadata.branch}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(cleanup_code, 0)
        self.assertIn("worktree removed", cleanup_stdout.getvalue())
        self.assertIn("branch deleted", cleanup_stdout.getvalue())
        self.assertFalse(worktree.exists())
        self.assertNotEqual(branch_check.returncode, 0)

    def test_cleanup_refuses_dirty_worktree_without_discard_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--repo-root", str(repo_root), "make", "Dirty cleanup"]), 0)
            task_path = Path(stdout.getvalue().strip())
            task = load_task(task_path)
            worktree = Path(task.metadata.worktree)
            (worktree / "app.py").write_text("print('dirty')\n", encoding="utf-8")

            blocked_stdout = io.StringIO()
            with redirect_stdout(blocked_stdout):
                blocked_code = main(["--repo-root", str(repo_root), "cleanup", str(task_path), "--force"])
            exists_after_block = worktree.exists()
            discard_stdout = io.StringIO()
            with redirect_stdout(discard_stdout):
                discard_code = main(
                    ["--repo-root", str(repo_root), "cleanup", str(task_path), "--force", "--discard-changes"]
                )

        self.assertEqual(blocked_code, 1)
        self.assertIn("worktree has local changes", blocked_stdout.getvalue())
        self.assertIn("app.py", blocked_stdout.getvalue())
        self.assertTrue(exists_after_block)
        self.assertEqual(discard_code, 0)
        self.assertIn("discarded local changes", discard_stdout.getvalue())
        self.assertFalse(worktree.exists())

    def test_full_cli_lifecycle_with_adapter_plan_and_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
            project_root = Path(__file__).resolve().parents[2]
            plan_adapter = project_root / "examples" / "adapters" / "static_plan_adapter.py"
            execute_adapter = project_root / "examples" / "adapters" / "file_write_execute_adapter.py"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--repo-root", str(repo_root), "make", "Adapter e2e"]), 0)
            task_path = Path(stdout.getvalue().strip())

            self.assertEqual(_run_cli(["--repo-root", str(repo_root), "run", "design", str(task_path)]), 0)
            update_task(
                task_path,
                section_updates={
                    "Repo Anchors": "- app.py",
                    "Docs Impact": "No documentation changes required.",
                },
                metadata_updates={"docs_status": "not_needed"},
            )
            self.assertEqual(
                _run_cli(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "plan",
                        str(task_path),
                        "--adapter-command",
                        f"{sys.executable} {plan_adapter}",
                    ]
                ),
                0,
            )
            self.assertEqual(
                _run_cli(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "execute",
                        str(task_path),
                        "--adapter-command",
                        f"{sys.executable} {execute_adapter}",
                    ]
                ),
                0,
            )
            self.assertEqual(
                _run_cli(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "verify",
                        str(task_path),
                        "--check",
                        f"{sys.executable} -c \"print('ok')\"",
                        "--manual-smoke",
                        "smoke-1:passed:observed adapter output",
                    ]
                ),
                0,
            )
            self.assertEqual(_run_cli(["--repo-root", str(repo_root), "run", "review", str(task_path)]), 0)
            self.assertEqual(_run_cli(["--repo-root", str(repo_root), "finish", str(task_path)]), 0)
            task = load_task(task_path)
            review = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(task.metadata.status, "done")
        self.assertEqual(review["outcome"], "pass")
        self.assertEqual(review["planned_scope"], ["app.py"])
        self.assertEqual(review["actual_scope"], ["app.py"])
        self.assertEqual(review["scope_mismatches"], [])

    def test_full_cli_lifecycle_with_review_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "AXIOM Test"], cwd=repo_root, check=True)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
            project_root = Path(__file__).resolve().parents[2]
            plan_adapter = project_root / "examples" / "adapters" / "static_plan_adapter.py"
            execute_adapter = project_root / "examples" / "adapters" / "file_write_execute_adapter.py"
            review_adapter = repo_root / "review_adapter.py"
            review_adapter.write_text(
                "import json, sys\n"
                "request = json.load(sys.stdin)\n"
                "assert request['phase'] == 'review'\n"
                "assert 'adapter changed' in request['diff']\n"
                "json.dump({'outcome': 'pass', 'summary': 'semantic pass', 'findings': [], 'next_phase': 'done'}, sys.stdout)\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--repo-root", str(repo_root), "make", "Review adapter e2e"]), 0)
            task_path = Path(stdout.getvalue().strip())
            self.assertEqual(_run_cli(["--repo-root", str(repo_root), "run", "design", str(task_path)]), 0)
            update_task(
                task_path,
                section_updates={
                    "Repo Anchors": "- app.py",
                    "Docs Impact": "No documentation changes required.",
                },
                metadata_updates={"docs_status": "not_needed"},
            )
            self.assertEqual(
                _run_cli(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "plan",
                        str(task_path),
                        "--adapter-command",
                        f"{sys.executable} {plan_adapter}",
                    ]
                ),
                0,
            )
            self.assertEqual(
                _run_cli(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "execute",
                        str(task_path),
                        "--adapter-command",
                        f"{sys.executable} {execute_adapter}",
                    ]
                ),
                0,
            )
            self.assertEqual(
                _run_cli(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "verify",
                        str(task_path),
                        "--check",
                        f"{sys.executable} -c \"print('ok')\"",
                        "--manual-smoke",
                        "smoke-1:passed:observed adapter output",
                    ]
                ),
                0,
            )
            self.assertEqual(
                _run_cli(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "review",
                        str(task_path),
                        "--adapter-command",
                        f"{sys.executable} {review_adapter}",
                    ]
                ),
                0,
            )
            self.assertEqual(_run_cli(["--repo-root", str(repo_root), "finish", str(task_path)]), 0)
            task = load_task(task_path)
            review = latest_phase_result(repo_root, task.metadata.id, "review")

        self.assertEqual(task.metadata.status, "done")
        self.assertEqual(review["outcome"], "pass")
        self.assertEqual(review["summary"], "semantic pass")
        self.assertEqual(review["adapter"]["status"], "passed")
