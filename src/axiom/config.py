from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoLayout:
    repo_root: Path

    @property
    def axiom_root(self) -> Path:
        return self.repo_root / ".axiom"

    @property
    def tasks_root(self) -> Path:
        return self.axiom_root / "tasks"

    @property
    def shared_artifacts_root(self) -> Path:
        return self.axiom_root / "artifacts" / "shared"

    @property
    def local_artifacts_root(self) -> Path:
        return self.axiom_root / "artifacts" / "local"

    @property
    def logs_root(self) -> Path:
        return self.axiom_root / "logs"

    def ensure(self) -> None:
        self.tasks_root.mkdir(parents=True, exist_ok=True)
        self.shared_artifacts_root.mkdir(parents=True, exist_ok=True)
        self.local_artifacts_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)


def layout_for(repo_root: Path) -> RepoLayout:
    return RepoLayout(repo_root=repo_root.resolve())
