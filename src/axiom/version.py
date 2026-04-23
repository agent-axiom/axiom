from __future__ import annotations

from dataclasses import dataclass

from . import _build


@dataclass(frozen=True)
class BuildMetadata:
    version: str
    git_commit: str
    git_tag: str
    build_timestamp: str
    source_repo: str

    def to_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "git_commit": self.git_commit,
            "git_tag": self.git_tag,
            "build_timestamp": self.build_timestamp,
            "source_repo": self.source_repo,
        }

    def verbose_lines(self) -> list[str]:
        return [f"{key}: {value}" for key, value in self.to_dict().items()]


def build_metadata() -> BuildMetadata:
    return BuildMetadata(
        version=_build.VERSION,
        git_commit=_build.GIT_COMMIT,
        git_tag=_build.GIT_TAG,
        build_timestamp=_build.BUILD_TIMESTAMP,
        source_repo=_build.SOURCE_REPO,
    )
