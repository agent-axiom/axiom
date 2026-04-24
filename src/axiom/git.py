from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import TaskDocument


@dataclass(frozen=True)
class WorkspacePlan:
    base_branch: str
    branch: str
    worktree: str
    bootstrap_reason: str = ""


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


class GitWorkspaceError(RuntimeError):
    pass


def is_git_repo(repo_root: Path) -> bool:
    if not (repo_root / ".git").exists():
        return False
    result = _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def has_head_commit(repo_root: Path) -> bool:
    if not is_git_repo(repo_root):
        return False
    result = _run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    return result.returncode == 0


def current_branch(repo_root: Path) -> str:
    if not is_git_repo(repo_root):
        return "main"
    result = _run_git(repo_root, ["symbolic-ref", "--short", "HEAD"])
    if result.returncode != 0:
        return "main"
    branch = result.stdout.strip()
    return branch or "main"


def choose_worktree_dir(repo_root: Path) -> Path:
    hidden = repo_root / ".worktrees"
    visible = repo_root / "worktrees"
    if hidden.exists():
        return hidden
    if visible.exists():
        return visible
    return hidden


def plan_workspace(repo_root: Path, task_id: str, slug: str) -> WorkspacePlan:
    branch = f"axiom/{task_id}-{slug}"
    worktree_dir = choose_worktree_dir(repo_root)
    worktree = worktree_dir / f"{task_id}-{slug}"
    if not is_git_repo(repo_root):
        return WorkspacePlan(
            base_branch="main",
            branch=branch,
            worktree=str(repo_root),
            bootstrap_reason="repository is not a git worktree",
        )
    if not has_head_commit(repo_root):
        return WorkspacePlan(
            base_branch=current_branch(repo_root),
            branch=branch,
            worktree=str(repo_root),
            bootstrap_reason="repository has no initial commit; worktree creation deferred",
        )
    return WorkspacePlan(
        base_branch=current_branch(repo_root),
        branch=branch,
        worktree=str(worktree),
    )


def _git_path(repo_root: Path, path_name: str) -> Path:
    result = _run_git(repo_root, ["rev-parse", "--git-path", path_name])
    if result.returncode != 0:
        raise GitWorkspaceError(result.stderr.strip() or f"could not resolve git path {path_name}")
    return (repo_root / result.stdout.strip()).resolve()


def ensure_worktree_dir_ignored(repo_root: Path) -> None:
    worktree_dir = choose_worktree_dir(repo_root)
    ignore_pattern = f"{worktree_dir.name}/"
    exclude_path = _git_path(repo_root, "info/exclude")
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    patterns = {line.strip() for line in existing.splitlines()}
    if ignore_pattern in patterns:
        return
    suffix = "" if existing.endswith("\n") or not existing else "\n"
    exclude_path.write_text(f"{existing}{suffix}{ignore_pattern}\n", encoding="utf-8")


def provision_workspace(repo_root: Path, task_id: str, slug: str) -> WorkspacePlan:
    workspace = plan_workspace(repo_root, task_id, slug)
    if workspace.bootstrap_reason:
        return workspace

    ensure_worktree_dir_ignored(repo_root)
    worktree = Path(workspace.worktree)
    if worktree.exists():
        if is_git_repo(worktree):
            return workspace
        raise GitWorkspaceError(f"worktree path already exists and is not a git worktree: {worktree}")

    worktree.parent.mkdir(parents=True, exist_ok=True)
    result = _run_git(repo_root, ["worktree", "add", "-b", workspace.branch, str(worktree), workspace.base_branch])
    if result.returncode != 0:
        raise GitWorkspaceError(result.stderr.strip() or "git worktree add failed")
    return workspace


def repo_changed_files(repo_root: Path) -> list[str]:
    if not is_git_repo(repo_root):
        return []
    result = _run_git(repo_root, ["status", "--short"])
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        files.append(line[3:].strip())
    return files


def changed_files_against_base(repo_root: Path, base_ref: str) -> list[str]:
    if not is_git_repo(repo_root):
        return []

    files: set[str] = set()
    result = _run_git(repo_root, ["diff", "--name-only", base_ref, "--"])
    if result.returncode == 0:
        files.update(line.strip() for line in result.stdout.splitlines() if line.strip())

    for file_name in repo_changed_files(repo_root):
        files.add(file_name)

    return sorted(files)


def diff_against_base(repo_root: Path, base_ref: str | None = None) -> str:
    if not is_git_repo(repo_root):
        return "No git repository detected."
    args = ["diff", "--"] if base_ref is None else ["diff", base_ref, "--"]
    result = _run_git(repo_root, args)
    if result.returncode != 0:
        return result.stderr.strip() or "git diff failed"
    output = result.stdout.strip()
    return output or "No local diff."


def task_workspace(task: TaskDocument) -> Path:
    return Path(task.metadata.worktree).resolve()


def task_changed_files(task: TaskDocument) -> list[str]:
    return changed_files_against_base(task_workspace(task), task.metadata.base_branch)


def task_diff(task: TaskDocument) -> str:
    diff = diff_against_base(task_workspace(task), task.metadata.base_branch)
    return "No task-scoped diff." if diff == "No local diff." else diff
