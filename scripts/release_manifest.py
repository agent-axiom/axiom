from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256_for(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(paths: list[Path]) -> str:
    lines = []
    for path in sorted(paths, key=lambda candidate: candidate.name):
        lines.append(f"{sha256_for(path)}  {path.name}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SHA-256 manifest entries")
    parser.add_argument("paths", nargs="+", help="Files to hash")
    args = parser.parse_args(argv)
    print(build_manifest([Path(value) for value in args.paths]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
