from __future__ import annotations

from pathlib import Path

from .models import TaskDocument, TaskMetadata

REQUIRED_SECTIONS = [
    "Objective",
    "Scope",
    "Invariants",
    "Assumptions",
    "Repo Anchors",
    "Design",
    "Plan",
    "Execution Log",
    "Verification",
    "Review",
    "Docs Impact",
]

FRONTMATTER_ORDER = [
    "id",
    "title",
    "kind",
    "status",
    "created_at",
    "updated_at",
    "repo_root",
    "base_branch",
    "base_commit",
    "branch",
    "worktree",
    "isolation_mode",
    "risk",
    "review_required",
    "verification_required",
    "manual_smoke_required",
    "docs_status",
    "blocked_reason",
]


def default_sections() -> dict[str, str]:
    sections = {section: "" for section in REQUIRED_SECTIONS}
    sections["Docs Impact"] = "Pending documentation decision."
    return sections


def render_new_task(
    *,
    task_id: str,
    title: str,
    kind: str,
    now_iso: str,
    repo_root: Path,
    base_branch: str,
    base_commit: str,
    branch: str,
    worktree: str,
    isolation_mode: str,
) -> TaskDocument:
    metadata = TaskMetadata(
        id=task_id,
        title=title,
        kind=kind,
        status="draft",
        created_at=now_iso,
        updated_at=now_iso,
        repo_root=str(repo_root),
        base_branch=base_branch,
        base_commit=base_commit,
        branch=branch,
        worktree=worktree,
        isolation_mode=isolation_mode,
        docs_status="pending",
    )
    return TaskDocument(metadata=metadata, title=title, sections=default_sections())
