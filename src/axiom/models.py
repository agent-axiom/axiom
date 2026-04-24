from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskMetadata:
    id: str
    title: str
    kind: str
    status: str
    created_at: str
    updated_at: str
    repo_root: str
    base_branch: str
    base_commit: str
    branch: str
    worktree: str
    isolation_mode: str = "degraded"
    risk: str = "medium"
    review_required: bool = True
    verification_required: bool = True
    manual_smoke_required: bool = True
    docs_status: str = "pending"
    blocked_reason: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "TaskMetadata":
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            kind=str(payload.get("kind", "feature")),
            status=str(payload.get("status", "draft")),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            repo_root=str(payload.get("repo_root", "")),
            base_branch=str(payload.get("base_branch", "main")),
            base_commit=str(payload.get("base_commit", "")),
            branch=str(payload.get("branch", "")),
            worktree=str(payload.get("worktree", "")),
            isolation_mode=str(payload.get("isolation_mode", "degraded")),
            risk=str(payload.get("risk", "medium")),
            review_required=bool(payload.get("review_required", True)),
            verification_required=bool(payload.get("verification_required", True)),
            manual_smoke_required=bool(payload.get("manual_smoke_required", True)),
            docs_status=str(payload.get("docs_status", "pending")),
            blocked_reason=str(payload.get("blocked_reason", "")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "repo_root": self.repo_root,
            "base_branch": self.base_branch,
            "base_commit": self.base_commit,
            "branch": self.branch,
            "worktree": self.worktree,
            "isolation_mode": self.isolation_mode,
            "risk": self.risk,
            "review_required": self.review_required,
            "verification_required": self.verification_required,
            "manual_smoke_required": self.manual_smoke_required,
            "docs_status": self.docs_status,
            "blocked_reason": self.blocked_reason,
        }

    def docs_resolved(self) -> bool:
        return self.docs_status in {"updated", "not_needed"}


@dataclass
class TaskDocument:
    metadata: TaskMetadata
    title: str
    sections: dict[str, str]
    path: Path | None = None


@dataclass
class FinishDecision:
    allowed: bool
    reason: str = ""
    artifact_path: Path | None = None


@dataclass
class CommandReceipt:
    name: str
    command: str
    status: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    policy: str = "allow"
    policy_reason: str = ""
    approval_id: str = ""
    approval_reason: str = ""
    approval_scope: dict[str, object] = field(default_factory=dict)


@dataclass
class PhaseSummary:
    phase: str
    outcome: str
    summary: str
    artifact_path: Path | None = None
    details: dict[str, object] = field(default_factory=dict)
