from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import TaskDocument

MAX_UNTRACKED_DIFF_BYTES = 64 * 1024
BINARY_DETECTION_SAMPLE_BYTES = 8192


@dataclass(frozen=True)
class WorkspacePlan:
    base_branch: str
    base_commit: str
    branch: str
    worktree: str
    isolation_mode: str
    bootstrap_reason: str = ""


@dataclass(frozen=True)
class CleanupResult:
    ok: bool
    messages: list[str]
    worktree_removed: bool = False
    branch_deleted: bool = False


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


def current_commit(repo_root: Path) -> str:
    if not has_head_commit(repo_root):
        return ""
    result = _run_git(repo_root, ["rev-parse", "HEAD"])
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


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
            base_commit="",
            branch=branch,
            worktree=str(repo_root),
            isolation_mode="degraded",
            bootstrap_reason="repository is not a git worktree",
        )
    if not has_head_commit(repo_root):
        return WorkspacePlan(
            base_branch=current_branch(repo_root),
            base_commit="",
            branch=branch,
            worktree=str(repo_root),
            isolation_mode="degraded",
            bootstrap_reason="repository has no initial commit; worktree creation deferred",
        )
    return WorkspacePlan(
        base_branch=current_branch(repo_root),
        base_commit=current_commit(repo_root),
        branch=branch,
        worktree=str(worktree),
        isolation_mode="worktree",
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
    base_ref = workspace.base_commit or workspace.base_branch
    result = _run_git(repo_root, ["worktree", "add", "-b", workspace.branch, str(worktree), base_ref])
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


def _untracked_files(repo_root: Path) -> list[str]:
    if not is_git_repo(repo_root):
        return []
    result = _run_git(repo_root, ["status", "--porcelain", "--untracked-files=all"])
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.startswith("?? "):
            continue
        file_name = line[3:].strip()
        if file_name:
            files.append(file_name)
    return sorted(files)


def _is_binary_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(BINARY_DETECTION_SAMPLE_BYTES)
    except OSError:
        return True
    if b"\0" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _omitted_untracked_diff(file_name: str, *, file_size: int) -> str:
    return "\n".join(
        [
            f"diff --git a/{file_name} b/{file_name}",
            "new file mode 100644",
            "--- /dev/null",
            f"+++ b/{file_name}",
            "@@ evidence omitted @@",
            "+content_omitted_reason: binary_or_too_large",
            f"+file_size_bytes: {file_size}",
            f"+max_untracked_diff_bytes: {MAX_UNTRACKED_DIFF_BYTES}",
        ]
    )


def _untracked_diff(repo_root: Path) -> str:
    chunks: list[str] = []
    for file_name in _untracked_files(repo_root):
        path = repo_root / file_name
        if not path.is_file():
            continue
        file_size = path.stat().st_size
        if file_size > MAX_UNTRACKED_DIFF_BYTES or _is_binary_file(path):
            chunks.append(_omitted_untracked_diff(file_name, file_size=file_size))
            continue
        result = _run_git(repo_root, ["diff", "--no-index", "--", "/dev/null", file_name])
        if result.stdout.strip():
            chunks.append(result.stdout.strip())
    return "\n\n".join(chunks)


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
    output = "\n\n".join(item for item in [result.stdout.strip(), _untracked_diff(repo_root)] if item)
    return output or "No local diff."


def task_workspace(task: TaskDocument) -> Path:
    return Path(task.metadata.worktree).resolve()


def task_base_ref(task: TaskDocument) -> str:
    return task.metadata.base_commit or task.metadata.base_branch


def task_changed_files(task: TaskDocument) -> list[str]:
    return changed_files_against_base(task_workspace(task), task_base_ref(task))


def task_diff(task: TaskDocument) -> str:
    diff = diff_against_base(task_workspace(task), task_base_ref(task))
    return "No task-scoped diff." if diff == "No local diff." else diff


def _branch_exists(repo_root: Path, branch: str) -> bool:
    if not branch:
        return False
    result = _run_git(repo_root, ["show-ref", "--verify", f"refs/heads/{branch}"])
    return result.returncode == 0


def cleanup_task_worktree(
    task: TaskDocument,
    *,
    force: bool = False,
    discard_changes: bool = False,
    dry_run: bool = False,
    only_if_done: bool = False,
    delete_branch: bool = False,
) -> CleanupResult:
    repo_root = Path(task.metadata.repo_root)
    worktree = task_workspace(task)
    branch = task.metadata.branch
    messages: list[str] = []

    if only_if_done and task.metadata.status != "done":
        return CleanupResult(False, [f"task is not done: {task.metadata.status}"])
    if task.metadata.isolation_mode != "worktree":
        return CleanupResult(False, ["task is not using a managed git worktree"])
    if not is_git_repo(repo_root):
        return CleanupResult(False, ["repository is not a git worktree"])

    if dry_run:
        if worktree.exists():
            messages.append(f"would remove worktree: {worktree}")
        else:
            messages.append(f"worktree already removed: {worktree}")
        if delete_branch:
            messages.append(f"would delete branch if merged: {branch}")
        else:
            messages.append(f"would keep branch: {branch}")
        return CleanupResult(True, messages)

    if not force:
        return CleanupResult(False, ["cleanup requires --force unless --dry-run is used"])

    worktree_removed = False
    if worktree.exists():
        dirty_files = repo_changed_files(worktree)
        if dirty_files and not discard_changes:
            return CleanupResult(
                False,
                [
                    "worktree has local changes; rerun with --discard-changes to remove it",
                    *[f"- {file_name}" for file_name in dirty_files],
                ],
            )
        args = ["worktree", "remove"]
        if discard_changes:
            args.append("--force")
        args.append(str(worktree))
        result = _run_git(repo_root, args)
        if result.returncode != 0:
            return CleanupResult(False, [result.stderr.strip() or "git worktree remove failed"])
        worktree_removed = True
        messages.append(f"worktree removed: {worktree}")
        if dirty_files and discard_changes:
            messages.append("discarded local changes")
    else:
        messages.append(f"worktree already removed: {worktree}")

    branch_deleted = False
    if delete_branch:
        if not _branch_exists(repo_root, branch):
            messages.append(f"branch already absent: {branch}")
        else:
            result = _run_git(repo_root, ["branch", "-d", branch])
            if result.returncode != 0:
                messages.append(result.stderr.strip() or f"git branch -d {branch} failed")
                return CleanupResult(False, messages, worktree_removed=worktree_removed)
            branch_deleted = True
            messages.append(f"branch deleted: {branch}")
    else:
        messages.append(f"branch kept: {branch}")

    return CleanupResult(True, messages, worktree_removed=worktree_removed, branch_deleted=branch_deleted)


def remove_task_worktree(task: TaskDocument, *, force: bool = False) -> tuple[bool, str]:
    result = cleanup_task_worktree(task, force=force, discard_changes=force)
    return result.ok, "\n".join(result.messages)
