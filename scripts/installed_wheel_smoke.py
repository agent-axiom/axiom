from __future__ import annotations

import argparse
import json
import shlex
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


def resolve_tool_path(value: str, *, cwd: Path | None = None) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    if "/" in value or "\\" in value:
        return str(((cwd or Path.cwd()) / path).resolve())
    return value


def assert_artifact_outcome(artifact_path: str, *, field: str, expected: str) -> None:
    path = Path(artifact_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual = payload.get(field)
    if actual != expected:
        formatted = json.dumps(payload, indent=2, sort_keys=True)
        raise RuntimeError(f"{path}: expected {field}={expected}, got {actual}\n{formatted}")


def adapter_command(python_bin: str, adapter_path: Path) -> str:
    return f"{shlex.quote(python_bin)} {shlex.quote(str(adapter_path))}"


def python_inline_command(python_bin: str, snippet: str) -> str:
    return f"{shlex.quote(python_bin)} -c {shlex.quote(snippet)}"


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
    invocation_cwd = Path.cwd()
    axiom_bin = resolve_tool_path(args.axiom_bin, cwd=invocation_cwd)
    python_bin = resolve_tool_path(args.python_bin, cwd=invocation_cwd)
    project_root = Path(__file__).resolve().parents[1]
    plan_adapter = project_root / "examples" / "adapters" / "static_plan_adapter.py"
    execute_adapter = project_root / "examples" / "adapters" / "file_write_execute_adapter.py"

    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        run(["git", "init", "-b", "main"], cwd=repo_root)
        run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root)
        run(["git", "config", "user.name", "AXIOM Smoke"], cwd=repo_root)
        (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
        run(["git", "add", "app.py"], cwd=repo_root)
        run(["git", "commit", "-m", "initial"], cwd=repo_root)

        task_path = Path(run([axiom_bin, "--repo-root", str(repo_root), "make", "Installed wheel smoke"]))
        replace_section(task_path, "Repo Anchors", "- app.py")
        replace_section(task_path, "Docs Impact", "No documentation changes required.")

        run([axiom_bin, "--repo-root", str(repo_root), "run", "design", str(task_path)])
        run(
            [
                axiom_bin,
                "--repo-root",
                str(repo_root),
                "run",
                "plan",
                str(task_path),
                "--adapter-command",
                adapter_command(python_bin, plan_adapter),
            ]
        )
        worktree = Path(run([axiom_bin, "--repo-root", str(repo_root), "worktree", "path", str(task_path)]))
        run(
            [
                axiom_bin,
                "--repo-root",
                str(repo_root),
                "run",
                "execute",
                str(task_path),
                "--adapter-command",
                adapter_command(python_bin, execute_adapter),
            ]
        )
        if "adapter changed" not in (worktree / "app.py").read_text(encoding="utf-8"):
            raise RuntimeError("execute adapter did not update app.py in the task worktree")
        verify_artifact = run(
            [
                axiom_bin,
                "--repo-root",
                str(repo_root),
                "run",
                "verify",
                str(task_path),
                "--check",
                python_inline_command(python_bin, "print('ok')"),
                "--manual-smoke",
                "smoke-1:passed:installed CLI smoke observed",
            ]
        )
        assert_artifact_outcome(verify_artifact, field="outcome", expected="passed")
        review_artifact = run([axiom_bin, "--repo-root", str(repo_root), "run", "review", str(task_path)])
        assert_artifact_outcome(review_artifact, field="outcome", expected="pass")
        run([axiom_bin, "--repo-root", str(repo_root), "finish", str(task_path)])

    print("installed wheel smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
