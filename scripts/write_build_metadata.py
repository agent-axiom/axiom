from __future__ import annotations

import argparse
from pathlib import Path


def render_build_module(
    *,
    version: str,
    git_commit: str,
    git_tag: str,
    build_timestamp: str,
    source_repo: str,
) -> str:
    return "\n".join(
        [
            '"""Embedded build metadata generated for release artifacts."""',
            "",
            f'VERSION = "{version}"',
            f'GIT_COMMIT = "{git_commit}"',
            f'GIT_TAG = "{git_tag}"',
            f'BUILD_TIMESTAMP = "{build_timestamp}"',
            f'SOURCE_REPO = "{source_repo}"',
            "",
        ]
    )


def write_build_module(
    *,
    output_path: Path,
    version: str,
    git_commit: str,
    git_tag: str,
    build_timestamp: str,
    source_repo: str,
) -> Path:
    rendered = render_build_module(
        version=version,
        git_commit=git_commit,
        git_tag=git_tag,
        build_timestamp=build_timestamp,
        source_repo=source_repo,
    )
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write embedded build metadata for AXIOM releases")
    parser.add_argument("--output", default="src/axiom/_build.py")
    parser.add_argument("--version", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--git-tag", required=True)
    parser.add_argument("--build-timestamp", required=True)
    parser.add_argument("--source-repo", required=True)
    args = parser.parse_args(argv)

    write_build_module(
        output_path=Path(args.output),
        version=args.version,
        git_commit=args.git_commit,
        git_tag=args.git_tag,
        build_timestamp=args.build_timestamp,
        source_repo=args.source_repo,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
