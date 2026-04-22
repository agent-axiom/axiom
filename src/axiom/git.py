from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


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


def diff_against_base(repo_root: Path) -> str:
    if not is_git_repo(repo_root):
        return "No git repository detected."
    result = _run_git(repo_root, ["diff", "--"])
    if result.returncode != 0:
        return result.stderr.strip() or "git diff failed"
    output = result.stdout.strip()
    return output or "No local diff."
