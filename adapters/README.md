# Adapters

AXIOM now ships a first adapter boundary: the command adapter protocol.

The protocol is intentionally small and local-first:
- AXIOM starts a local command supplied by the user or platform team.
- AXIOM sends one JSON request to the command on stdin.
- The adapter returns one JSON object on stdout.
- The adapter runs in the task worktree, not the source checkout.
- AXIOM validates phase outputs before persisting artifacts.

Protocol name:

```text
axiom.adapter.v1
```

Current integration points:
- `axiom run plan <task> --adapter-command "..."`
- `axiom run execute <task> --adapter-command "..."`
- `axiom adapter list`

Adapter request shape:

```json
{
  "protocol": "axiom.adapter.v1",
  "phase": "plan",
  "task": {
    "id": "AX-20260424-001",
    "title": "fix retry logic",
    "kind": "feature",
    "status": "design.passed",
    "risk": "medium"
  },
  "task_path": "/repo/.axiom/tasks/2026/04/AX-20260424-001-fix-retry-logic.md",
  "repo_root": "/repo",
  "workspace": "/repo/.worktrees/AX-20260424-001-fix-retry-logic",
  "base_branch": "main",
  "branch": "axiom/AX-20260424-001-fix-retry-logic",
  "sections": {},
  "latest_artifacts": {},
  "diff": ""
}
```

For `plan`, the adapter must return a payload matching `schemas/plan.schema.json`.

For `execute`, the adapter may edit files in the task worktree and should return:

```json
{
  "summary": "Applied the requested change."
}
```

AXIOM records the adapter receipt, changed files before execution, changed files after execution, and newly changed files.

Still deferred:
- built-in vendor-specific model adapters
- built-in local model server clients
- long-running agent sessions
- streaming adapter output
- automatic approval of escalated tools
