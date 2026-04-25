from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def run(argv: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        command = " ".join(argv)
        raise RuntimeError(f"{command} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result.stdout.strip()


def replace_section(task_path: Path, section: str, content: str) -> None:
    text = task_path.read_text(encoding="utf-8")
    marker = f"## {section}\n"
    start = text.index(marker) + len(marker)
    next_section = text.find("\n## ", start)
    if next_section == -1:
        updated = text[:start] + content.rstrip() + "\n"
    else:
        updated = text[:start] + content.rstrip() + "\n" + text[next_section:]
    task_path.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axiom-bin", default="axiom")
    parser.add_argument("--python-bin", default=sys.executable)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        run(["git", "init", "-b", "main"], cwd=repo_root)
        run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root)
        run(["git", "config", "user.name", "AXIOM Smoke"], cwd=repo_root)
        (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
        run(["git", "add", "app.py"], cwd=repo_root)
        run(["git", "commit", "-m", "initial"], cwd=repo_root)

        task_path = Path(run([args.axiom_bin, "--repo-root", str(repo_root), "make", "Installed wheel smoke"]))
        replace_section(task_path, "Repo Anchors", "- app.py")
        replace_section(task_path, "Docs Impact", "No documentation changes required.")

        run([args.axiom_bin, "--repo-root", str(repo_root), "run", "design", str(task_path)])
        run([args.axiom_bin, "--repo-root", str(repo_root), "run", "plan", str(task_path)])
        worktree = Path(run([args.axiom_bin, "--repo-root", str(repo_root), "worktree", "path", str(task_path)]))
        (worktree / "app.py").write_text("print('installed smoke changed')\n", encoding="utf-8")
        run([args.axiom_bin, "--repo-root", str(repo_root), "run", "execute", str(task_path), "--note", "Smoke edit recorded."])
        run(
            [
                args.axiom_bin,
                "--repo-root",
                str(repo_root),
                "run",
                "verify",
                str(task_path),
                "--check",
                f"{args.python_bin} -c \"print('ok')\"",
                "--manual-smoke",
                "smoke-1:passed:installed CLI smoke observed",
            ]
        )
        run([args.axiom_bin, "--repo-root", str(repo_root), "run", "review", str(task_path)])
        run([args.axiom_bin, "--repo-root", str(repo_root), "finish", str(task_path)])

    print("installed wheel smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
