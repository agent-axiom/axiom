from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.artifacts import latest_phase_result
from axiom.cli import main
from axiom.git import MAX_UNTRACKED_DIFF_BYTES
from axiom.phases import run_design, run_execute, run_plan
from axiom.task_file import create_task, load_task


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _init_repo(repo_root: Path, *, with_commit: bool = True) -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "axiom@example.test")
    _git(repo_root, "config", "user.name", "AXIOM Test")
    (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    if with_commit:
        _git(repo_root, "add", "app.py", "README.md")
        _git(repo_root, "commit", "-m", "initial")


class GitRuntimeTest(unittest.TestCase):
    def test_create_task_provisions_isolated_git_worktree_for_repo_with_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)

            task_path = create_task(
                repo_root=repo_root,
                title="Task isolation",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            worktree = Path(task.metadata.worktree)

            self.assertNotEqual(worktree.resolve(), repo_root.resolve())
            self.assertTrue(worktree.exists())
            self.assertTrue((worktree / "app.py").exists())
            self.assertEqual(_git(worktree, "branch", "--show-current").stdout.strip(), task.metadata.branch)
            self.assertEqual(_git(repo_root, "check-ignore", "-q", ".worktrees", check=False).returncode, 0)
            self.assertEqual(task.metadata.isolation_mode, "worktree")
            self.assertEqual(task.metadata.base_commit, _git(repo_root, "rev-parse", "HEAD").stdout.strip())

    def test_create_task_records_bootstrap_fallback_for_git_repo_without_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root, with_commit=False)

            task_path = create_task(
                repo_root=repo_root,
                title="No head fallback",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)

            self.assertEqual(Path(task.metadata.worktree).resolve(), repo_root.resolve())
            self.assertEqual(task.metadata.isolation_mode, "degraded")
            self.assertEqual(task.metadata.base_commit, "")
            self.assertIn("repository has no initial commit", task.sections["Assumptions"])

    def test_task_diff_uses_immutable_base_commit_not_moving_base_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)
            task_path = create_task(
                repo_root=repo_root,
                title="Immutable base",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            base_commit = task.metadata.base_commit
            self.assertTrue(base_commit)

            (repo_root / "app.py").write_text("print('main advanced')\n", encoding="utf-8")
            _git(repo_root, "add", "app.py")
            _git(repo_root, "commit", "-m", "advance main")

            worktree = Path(task.metadata.worktree)
            (worktree / "app.py").write_text("print('task change')\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "diff", str(task_path)])
            diff_output = stdout.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("-print('base')", diff_output)
        self.assertIn("+print('task change')", diff_output)
        self.assertNotIn("-print('main advanced')", diff_output)

    def test_diff_command_uses_task_worktree_not_dirty_source_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)
            task_path = create_task(
                repo_root=repo_root,
                title="Scoped diff",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            worktree = Path(task.metadata.worktree)
            (worktree / "app.py").write_text("print('task change')\n", encoding="utf-8")
            (repo_root / "README.md").write_text("dirty source checkout\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "diff", str(task_path)])

            diff_output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("task change", diff_output)
            self.assertIn("app.py", diff_output)
            self.assertNotIn("dirty source checkout", diff_output)

    def test_diff_command_includes_untracked_file_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)
            task_path = create_task(
                repo_root=repo_root,
                title="New file evidence",
                kind="feature",
                now=datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            worktree = Path(task.metadata.worktree)
            (worktree / "new_feature.py").write_text("print('new evidence')\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "diff", str(task_path)])

            diff_output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("new_feature.py", diff_output)
            self.assertIn("+print('new evidence')", diff_output)

    def test_diff_command_omits_large_untracked_file_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)
            task_path = create_task(
                repo_root=repo_root,
                title="Large file evidence",
                kind="feature",
                now=datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            marker = "large-content-marker"
            Path(task.metadata.worktree, "large.log").write_text(
                marker + ("x" * MAX_UNTRACKED_DIFF_BYTES),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "diff", str(task_path)])

            diff_output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("large.log", diff_output)
            self.assertIn("content_omitted_reason: binary_or_too_large", diff_output)
            self.assertNotIn(marker, diff_output)

    def test_diff_command_omits_binary_untracked_file_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)
            task_path = create_task(
                repo_root=repo_root,
                title="Binary file evidence",
                kind="feature",
                now=datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            Path(task.metadata.worktree, "image.bin").write_bytes(b"\x00\x01binary")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "diff", str(task_path)])

            diff_output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("image.bin", diff_output)
            self.assertIn("content_omitted_reason: binary_or_too_large", diff_output)
            self.assertNotIn("\\x00", diff_output)

    def test_execute_records_changed_files_from_task_worktree_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_repo(repo_root)
            task_path = create_task(
                repo_root=repo_root,
                title="Scoped execute",
                kind="feature",
                now=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
            )
            run_design(task_path)
            run_plan(task_path)
            task = load_task(task_path)
            worktree = Path(task.metadata.worktree)
            (worktree / "app.py").write_text("print('task change')\n", encoding="utf-8")
            (repo_root / "README.md").write_text("dirty source checkout\n", encoding="utf-8")

            run_execute(task_path, note="Applied scoped edit")
            result = latest_phase_result(repo_root, task.metadata.id, "execute")

            self.assertEqual(result["changed_files"], ["app.py"])
