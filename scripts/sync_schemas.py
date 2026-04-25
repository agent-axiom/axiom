from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _schema_names(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {path.name for path in root.glob("*.json") if path.is_file()}


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def check_schemas(source_root: Path, packaged_root: Path) -> list[str]:
    source_names = _schema_names(source_root)
    packaged_names = _schema_names(packaged_root)
    issues: list[str] = []

    for name in sorted(source_names - packaged_names):
        issues.append(f"missing packaged schema: {name}")
    for name in sorted(packaged_names - source_names):
        issues.append(f"extra packaged schema: {name}")
    for name in sorted(source_names & packaged_names):
        if _load_json(source_root / name) != _load_json(packaged_root / name):
            issues.append(f"schema drift: {name}")

    return issues


def sync_schemas(source_root: Path, packaged_root: Path) -> None:
    packaged_root.mkdir(parents=True, exist_ok=True)
    source_names = _schema_names(source_root)
    for path in sorted(packaged_root.glob("*.json")):
        if path.name not in source_names:
            path.unlink()
    for name in sorted(source_names):
        shutil.copy2(source_root / name, packaged_root / name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or sync packaged AXIOM JSON schemas.")
    parser.add_argument("--source", type=Path, default=Path("schemas"))
    parser.add_argument("--packaged", type=Path, default=Path("src/axiom/schemas"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if packaged schemas drift from source schemas")
    mode.add_argument("--write", action="store_true", help="sync packaged schemas from source schemas")
    args = parser.parse_args()

    if args.write:
        sync_schemas(args.source, args.packaged)
        return 0

    issues = check_schemas(args.source, args.packaged)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("schemas in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
