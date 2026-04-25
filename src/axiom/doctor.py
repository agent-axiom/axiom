from __future__ import annotations

import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .git import choose_worktree_dir, has_head_commit, is_git_repo
from .schema import _load_schema


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    summary: str
    details: dict[str, Any]


SCHEMA_NAMES = [
    "adapter-request",
    "design",
    "execute",
    "finish",
    "plan",
    "review",
    "task-frontmatter",
    "verify",
]


def _runtime_mode() -> str:
    package_root = Path(__file__).resolve().parent
    return "source" if (package_root.parents[1] / "pyproject.toml").exists() else "installed"


def _check(name: str, status: str, summary: str, **details: Any) -> DoctorCheck:
    return DoctorCheck(name=name, status=status, summary=summary, details=details)


def run_doctor(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    checks: list[DoctorCheck] = []

    checks.append(
        _check(
            "python version",
            "pass" if sys.version_info >= (3, 11) else "fail",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            executable=sys.executable,
            required=">=3.11",
        )
    )

    missing_schemas = [name for name in SCHEMA_NAMES if _load_schema(name) is None]
    checks.append(
        _check(
            "schema availability",
            "pass" if not missing_schemas else "fail",
            "all runtime schemas available" if not missing_schemas else "runtime schemas missing",
            missing=missing_schemas,
        )
    )

    git_path = shutil.which("git")
    checks.append(
        _check(
            "git executable",
            "pass" if git_path else "fail",
            git_path or "git not found on PATH",
        )
    )

    git_repo = is_git_repo(repo_root)
    checks.append(
        _check(
            "git repository",
            "pass" if git_repo else "warn",
            "repo root is a git worktree" if git_repo else "repo root is not a git worktree; AXIOM will use degraded mode",
            repo_root=str(repo_root),
        )
    )

    has_head = has_head_commit(repo_root)
    checks.append(
        _check(
            "git head",
            "pass" if has_head else "warn",
            "HEAD commit exists" if has_head else "no HEAD commit; AXIOM cannot provision isolated worktrees yet",
        )
    )

    worktree_dir = choose_worktree_dir(repo_root)
    worktree_parent = worktree_dir.parent
    worktree_ready = git_repo and has_head and os.access(worktree_parent, os.W_OK)
    checks.append(
        _check(
            "worktree readiness",
            "pass" if worktree_ready else "warn",
            "git worktree provisioning available"
            if worktree_ready
            else "worktree provisioning unavailable; tasks may run degraded",
            worktree_dir=str(worktree_dir),
            parent_writable=os.access(worktree_parent, os.W_OK),
        )
    )

    checks.append(
        _check(
            "write permissions",
            "pass" if os.access(repo_root, os.W_OK) else "fail",
            "repo root is writable" if os.access(repo_root, os.W_OK) else "repo root is not writable",
            repo_root=str(repo_root),
        )
    )

    allowlist = os.environ.get("AXIOM_ADAPTER_ALLOWLIST", "")
    pins = os.environ.get("AXIOM_ADAPTER_SHA256", "")
    checks.append(
        _check(
            "adapter trust config",
            "pass",
            "adapter allowlist/hash pins detected" if allowlist or pins else "no adapter allowlist/hash pins configured",
            allowlist_configured=bool(allowlist),
            hash_pins_configured=bool(pins),
        )
    )

    checks.append(
        _check(
            "policy profiles",
            "pass",
            "known policy profiles are available",
            profiles=["standard", "strict", "permissive"],
        )
    )

    statuses = [check.status for check in checks]
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    return {
        "overall": overall,
        "runtime_mode": _runtime_mode(),
        "repo_root": str(repo_root),
        "checks": [asdict(check) for check in checks],
    }


def render_doctor(payload: dict[str, Any]) -> str:
    lines = [
        f"overall: {payload['overall']}",
        f"runtime_mode: {payload['runtime_mode']}",
        f"repo_root: {payload['repo_root']}",
    ]
    for check in payload["checks"]:
        lines.append(f"{check['status']}\t{check['name']}\t{check['summary']}")
    return "\n".join(lines)
