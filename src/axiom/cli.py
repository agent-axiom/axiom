from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .approvals import approve_command, list_approvals
from .doctor import render_doctor, run_doctor
from .git import cleanup_task_worktree, task_diff
from .phases import PhaseTransitionError, finish_task, run_design, run_execute, run_plan, run_review, run_verify
from .task_file import create_task, list_task_paths, load_task, resolve_task_path
from .tool_broker import DEFAULT_COMMAND_TIMEOUT_SECONDS, DEFAULT_MAX_OUTPUT_CHARS
from .version import build_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axiom")
    parser.add_argument("--repo-root", default=".", help="Repository root to operate in")
    subparsers = parser.add_subparsers(dest="command", required=True)

    make_parser = subparsers.add_parser("make", help="Create a new task file")
    make_parser.add_argument("title")
    make_parser.add_argument("--kind", default="feature")

    version_parser = subparsers.add_parser("version", help="Show AXIOM version metadata")
    version_parser.add_argument("--verbose", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Check local AXIOM runtime readiness")
    doctor_parser.add_argument("--json", action="store_true")

    adapter_parser = subparsers.add_parser("adapter", help="Inspect agent adapter support")
    adapter_subparsers = adapter_parser.add_subparsers(dest="adapter_command", required=True)
    adapter_subparsers.add_parser("list", help="List built-in adapter protocols")

    worktree_parser = subparsers.add_parser("worktree", help="Inspect task worktrees")
    worktree_subparsers = worktree_parser.add_subparsers(dest="worktree_command", required=True)
    worktree_subparsers.add_parser("list", help="List task worktrees")
    worktree_path_parser = worktree_subparsers.add_parser("path", help="Print a task worktree path")
    worktree_path_parser.add_argument("task")

    cleanup_parser = subparsers.add_parser("cleanup", help="Remove a managed task worktree")
    cleanup_parser.add_argument("task")
    cleanup_parser.add_argument("--force", action="store_true", help="Allow git worktree removal")
    cleanup_parser.add_argument("--discard-changes", action="store_true", help="Remove dirty worktree changes")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="Print cleanup actions without changing files")
    cleanup_parser.add_argument("--only-if-done", action="store_true", help="Refuse cleanup unless task status is done")
    branch_policy = cleanup_parser.add_mutually_exclusive_group()
    branch_policy.add_argument("--delete-branch", action="store_true", help="Delete the task branch with safe git branch -d")
    branch_policy.add_argument("--keep-branch", action="store_true", help="Keep the task branch after removing the worktree")

    policy_parser = subparsers.add_parser("policy", help="Manage local AXIOM policy approvals")
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command", required=True)
    approve_parser = policy_subparsers.add_parser("approve", help="Persist approval for an escalated command")
    approve_parser.add_argument("--command", dest="policy_target_command", required=True)
    approve_parser.add_argument("--reason", required=True)
    approve_parser.add_argument("--task", help="Scope approval to a task id or task file")
    policy_subparsers.add_parser("approvals", help="List persisted approvals")

    subparsers.add_parser("list", help="List tasks")

    show_parser = subparsers.add_parser("show", help="Show a task")
    show_parser.add_argument("task")

    resume_parser = subparsers.add_parser("resume", help="Show current status and next step")
    resume_parser.add_argument("task")

    diff_parser = subparsers.add_parser("diff", help="Show repository diff")
    diff_parser.add_argument("task")

    run_parser = subparsers.add_parser("run", help="Run a workflow phase")
    run_subparsers = run_parser.add_subparsers(dest="phase", required=True)

    design_parser = run_subparsers.add_parser("design")
    design_parser.add_argument("task")
    design_parser.add_argument("--force", action="store_true")

    plan_parser = run_subparsers.add_parser("plan")
    plan_parser.add_argument("task")
    plan_parser.add_argument("--adapter-command")
    plan_parser.add_argument("--force", action="store_true")

    execute_parser = run_subparsers.add_parser("execute")
    execute_parser.add_argument("task")
    execute_parser.add_argument("--note", default="Execution recorded.")
    execute_parser.add_argument("--adapter-command")
    execute_parser.add_argument("--force", action="store_true")

    verify_parser = run_subparsers.add_parser("verify")
    verify_parser.add_argument("task")
    verify_parser.add_argument("--check", action="append", default=[])
    verify_parser.add_argument("--negative-check", action="append", default=[])
    verify_parser.add_argument("--manual-smoke", action="append", default=[])
    verify_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_COMMAND_TIMEOUT_SECONDS)
    verify_parser.add_argument("--max-output-chars", type=int, default=DEFAULT_MAX_OUTPUT_CHARS)
    verify_parser.add_argument("--policy-profile", choices=["standard", "strict", "permissive"], default="standard")
    verify_parser.add_argument("--policy-allow", action="append", default=[])
    verify_parser.add_argument("--force", action="store_true")

    review_parser = run_subparsers.add_parser("review")
    review_parser.add_argument("task")
    review_parser.add_argument("--adapter-command")
    review_parser.add_argument("--force", action="store_true")

    finish_parser = subparsers.add_parser("finish", help="Complete a task")
    finish_parser.add_argument("task")

    return parser


def _parse_manual_smoke(entries: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for entry in entries:
        parts = entry.split(":", 2)
        if len(parts) < 3:
            raise ValueError(
                f"manual smoke entry must use id:status:notes format, got {entry!r}"
            )
        parsed.append({"id": parts[0], "status": parts[1], "notes": parts[2]})
    return parsed


def _next_step_for(status: str) -> str:
    if status == "draft":
        return "run design"
    if status == "design.passed":
        return "run plan"
    if status == "plan.blocked":
        return "fix adapter/planner input, then run plan"
    if status == "plan.passed":
        return "run execute"
    if status == "execute.failed":
        return "fix adapter/execution issue, then run execute"
    if status == "execute.passed":
        return "run verify"
    if status in {"verify.failed", "verify.blocked", "review.changes_requested"}:
        return "run execute"
    if status == "verify.passed":
        return "run review"
    if status == "review.passed":
        return "finish"
    if status == "done":
        return "none"
    return "inspect task"


def _print_task_summary(task_path: Path) -> None:
    task = load_task(task_path)
    print(task.title)
    print(f"id: {task.metadata.id}")
    print(f"status: {task.metadata.status}")
    print(f"path: {task_path}")
    print(f"base_commit: {task.metadata.base_commit}")
    print(f"branch: {task.metadata.branch}")
    print(f"worktree: {task.metadata.worktree}")
    print(f"isolation_mode: {task.metadata.isolation_mode}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if args.command == "make":
        task_path = create_task(repo_root=repo_root, title=args.title, kind=args.kind)
        print(task_path)
        return 0

    if args.command == "version":
        metadata = build_metadata()
        if args.verbose:
            print("\n".join(metadata.verbose_lines()))
        else:
            print(metadata.version)
        return 0

    if args.command == "doctor":
        payload = run_doctor(repo_root)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(render_doctor(payload))
        return 1 if payload["overall"] == "fail" else 0

    if args.command == "adapter":
        if args.adapter_command == "list":
            print("command\taxiom.adapter.v1 JSON over stdin/stdout")
            return 0

    if args.command == "worktree":
        if args.worktree_command == "list":
            for task_path in list_task_paths(repo_root):
                task = load_task(task_path)
                print(f"{task.metadata.id} {task.metadata.status} {task.metadata.isolation_mode} {task.metadata.worktree}")
            return 0
        if args.worktree_command == "path":
            task_path = resolve_task_path(repo_root, args.task)
            task = load_task(task_path)
            print(task.metadata.worktree)
            return 0

    if args.command == "cleanup":
        task_path = resolve_task_path(repo_root, args.task)
        task = load_task(task_path)
        result = cleanup_task_worktree(
            task,
            force=args.force,
            discard_changes=args.discard_changes,
            dry_run=args.dry_run,
            only_if_done=args.only_if_done,
            delete_branch=args.delete_branch,
        )
        print("\n".join(result.messages))
        return 0 if result.ok else 1

    if args.command == "policy":
        if args.policy_command == "approve":
            task_id = ""
            worktree = ""
            if args.task:
                task_path = resolve_task_path(repo_root, args.task)
                task = load_task(task_path)
                task_id = task.metadata.id
                worktree = task.metadata.worktree
            approval_id = approve_command(
                repo_root,
                args.policy_target_command,
                reason=args.reason,
                task_id=task_id,
                worktree=worktree,
            )
            print(approval_id)
            return 0
        if args.policy_command == "approvals":
            print(json.dumps(list_approvals(repo_root), indent=2, sort_keys=True))
            return 0

    if args.command == "list":
        for task_path in list_task_paths(repo_root):
            task = load_task(task_path)
            print(f"{task.metadata.id} {task.metadata.status} {task.title}")
        return 0

    if args.command == "show":
        task_path = resolve_task_path(repo_root, args.task)
        _print_task_summary(task_path)
        return 0

    if args.command == "resume":
        task_path = resolve_task_path(repo_root, args.task)
        task = load_task(task_path)
        _print_task_summary(task_path)
        print(f"next: {_next_step_for(task.metadata.status)}")
        return 0

    if args.command == "diff":
        task_path = resolve_task_path(repo_root, args.task)
        task = load_task(task_path)
        print(task_diff(task))
        return 0

    if args.command == "run":
        task_path = resolve_task_path(repo_root, args.task)
        try:
            if args.phase == "design":
                artifact = run_design(task_path, force=args.force)
            elif args.phase == "plan":
                artifact = run_plan(task_path, adapter_command=args.adapter_command, force=args.force)
            elif args.phase == "execute":
                artifact = run_execute(
                    task_path,
                    note=args.note,
                    adapter_command=args.adapter_command,
                    force=args.force,
                )
            elif args.phase == "verify":
                manual_smoke = _parse_manual_smoke(args.manual_smoke)
                artifact = run_verify(
                    task_path,
                    commands=args.check,
                    negative_commands=args.negative_check,
                    manual_smoke=manual_smoke,
                    timeout_seconds=args.timeout_seconds,
                    max_output_chars=args.max_output_chars,
                    policy_profile=args.policy_profile,
                    command_allowlist=args.policy_allow,
                    force=args.force,
                )
            elif args.phase == "review":
                artifact = run_review(task_path, adapter_command=args.adapter_command, force=args.force)
            else:
                parser.error(f"unsupported phase {args.phase}")
                return 2
        except PhaseTransitionError as exc:
            print(str(exc))
            return 1
        print(artifact)
        return 0

    if args.command == "finish":
        task_path = resolve_task_path(repo_root, args.task)
        decision = finish_task(task_path)
        if decision.allowed:
            print(f"finished: {task_path}")
            return 0
        print(decision.reason)
        return 1

    parser.error("unsupported command")
    return 2


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    entrypoint()
