from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


def run(argv: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        command = " ".join(argv)
        raise RuntimeError(f"{command} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result.stdout.strip()


@dataclass
class SmokeContext:
    repo_root: Path | None = None
    task_path: Path | None = None
    worktree: Path | None = None
    axiom_bin: str = ""


class SmokeFailure(RuntimeError):
    def __init__(self, diagnostics: str) -> None:
        super().__init__("installed wheel smoke failed")
        self.diagnostics = diagnostics


def _run_diagnostic_command(argv: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    output = "\n".join(item for item in [result.stdout.strip(), result.stderr.strip()] if item)
    return output or f"exit_code={result.returncode}"


def _latest_artifact_text(repo_root: Path) -> str:
    artifact_root = repo_root / ".axiom" / "artifacts"
    if not artifact_root.exists():
        return "no artifacts found"
    parts: list[str] = []
    for artifact in sorted(artifact_root.glob("**/result.json"))[-8:]:
        try:
            body = artifact.read_text(encoding="utf-8")
        except OSError as exc:
            body = f"could not read artifact: {exc}"
        parts.append(f"### {artifact.relative_to(repo_root)}\n{body}")
    return "\n\n".join(parts) if parts else "no result artifacts found"


def collect_failure_diagnostics(context: SmokeContext, error: BaseException) -> str:
    lines = [
        "## AXIOM installed-wheel smoke diagnostics",
        f"error: {error}",
        f"repo_root: {context.repo_root or 'unknown'}",
        f"task_path: {context.task_path or 'unknown'}",
        f"worktree: {context.worktree or 'unknown'}",
    ]
    if context.task_path and context.task_path.exists():
        lines.extend(["", "## task file", context.task_path.read_text(encoding="utf-8")])
    if context.repo_root and context.axiom_bin and context.task_path:
        lines.extend(
            [
                "",
                "## resume",
                _run_diagnostic_command(
                    [context.axiom_bin, "--repo-root", str(context.repo_root), "resume", str(context.task_path)]
                ),
                "",
                "## diff",
                _run_diagnostic_command(
                    [context.axiom_bin, "--repo-root", str(context.repo_root), "diff", str(context.task_path)]
                ),
                "",
                "## worktree path",
                _run_diagnostic_command(
                    [context.axiom_bin, "--repo-root", str(context.repo_root), "worktree", "path", str(context.task_path)]
                ),
            ]
        )
    if context.repo_root:
        lines.extend(["", "## latest artifacts", _latest_artifact_text(context.repo_root)])
    return "\n".join(lines)


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


def write_smoke_adapters(adapter_dir: Path) -> tuple[Path, Path]:
    adapter_dir.mkdir(parents=True, exist_ok=True)
    plan_adapter = adapter_dir / "plan_adapter.py"
    execute_adapter = adapter_dir / "execute_adapter.py"
    plan_adapter.write_text(
        """from __future__ import annotations

import json
import sys


def main() -> int:
    request = json.load(sys.stdin)
    anchors = []
    for line in request.get("sections", {}).get("Repo Anchors", "").splitlines():
        anchor = line.strip().lstrip("-*").strip().strip("`")
        if anchor:
            anchors.append(anchor)
    if not anchors:
        anchors = ["app.py"]
    json.dump(
        {
            "summary": "Smoke adapter plan.",
            "steps": [
                {
                    "id": "step-1",
                    "title": f"Apply the installed-wheel smoke change in {anchors[0]}.",
                    "write_scope": anchors,
                    "checks": [],
                }
            ],
            "manual_smoke": [
                {
                    "id": "smoke-1",
                    "instruction": "Observe installed CLI smoke output.",
                }
            ],
            "stop_conditions": ["Stop if installed CLI smoke cannot edit app.py."],
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    execute_adapter.write_text(
        """from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    request = json.load(sys.stdin)
    workspace = Path(str(request["workspace"]))
    (workspace / "app.py").write_text("print('adapter changed')\\n", encoding="utf-8")
    json.dump({"summary": "Smoke execute adapter updated app.py."}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    return plan_adapter, execute_adapter


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


def run_smoke(*, axiom_bin: str, python_bin: str, context: SmokeContext) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            tmp_root = Path(tmp)
            repo_root = tmp_root / "repo"
            repo_root.mkdir()
            context.repo_root = repo_root
            context.axiom_bin = axiom_bin
            plan_adapter, execute_adapter = write_smoke_adapters(tmp_root / "adapters")
            run(["git", "init", "-b", "main"], cwd=repo_root)
            run(["git", "config", "user.email", "axiom@example.test"], cwd=repo_root)
            run(["git", "config", "user.name", "AXIOM Smoke"], cwd=repo_root)
            (repo_root / "app.py").write_text("print('base')\n", encoding="utf-8")
            run(["git", "add", "app.py"], cwd=repo_root)
            run(["git", "commit", "-m", "initial"], cwd=repo_root)

            task_path = Path(run([axiom_bin, "--repo-root", str(repo_root), "make", "Installed wheel smoke"]))
            context.task_path = task_path
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
            context.worktree = worktree
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
        except Exception as exc:
            raise SmokeFailure(collect_failure_diagnostics(context, exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axiom-bin", default="axiom")
    parser.add_argument("--python-bin", default=sys.executable)
    args = parser.parse_args()
    invocation_cwd = Path.cwd()
    axiom_bin = resolve_tool_path(args.axiom_bin, cwd=invocation_cwd)
    python_bin = resolve_tool_path(args.python_bin, cwd=invocation_cwd)
    context = SmokeContext(axiom_bin=axiom_bin)
    try:
        run_smoke(axiom_bin=axiom_bin, python_bin=python_bin, context=context)
    except SmokeFailure as exc:
        print(exc.diagnostics, file=sys.stderr)
        return 1

    print("installed wheel smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
