# Adapters

AXIOM now ships a first adapter boundary: the command adapter protocol.

The protocol is intentionally small and local-first:
- AXIOM starts a local command supplied by the user or platform team.
- AXIOM sends one JSON request to the command on stdin.
- The adapter returns one JSON object on stdout.
- The adapter runs in the task worktree, not the source checkout.
- AXIOM validates phase outputs before persisting artifacts.
- AXIOM persists adapter failures as phase artifacts for debugging.

Security boundary:
- Command adapters are trusted local commands, not sandboxes.
- They run as the current OS user and can access files available to that user.
- Use `AXIOM_ADAPTER_ALLOWLIST` to restrict allowed adapter paths.
- Use `AXIOM_ADAPTER_SHA256` to pin adapter file hashes as `absolute_path=sha256`.

Protocol name:

```text
axiom.adapter.v1
```

Current integration points:
- `axiom run plan <task> --adapter-command "..."`
- `axiom run execute <task> --adapter-command "..."`
- `axiom run review <task> --adapter-command "..."`
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
  "base_commit": "9f2b1d8f0e4d7d7efc4b0e9a8b2c64e25f735b61",
  "branch": "axiom/AX-20260424-001-fix-retry-logic",
  "isolation_mode": "worktree",
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

For `review`, the adapter returns `schemas/review.schema.json`. Review adapters are semantic add-ons only: deterministic AXIOM gates for verification, docs, task diff, and plan write scope still run first and cannot be bypassed by an adapter pass.

Full protocol spec:
- `docs/ADAPTER_PROTOCOL.md`

Reference adapters:
- `examples/adapters/static_plan_adapter.py`
- `examples/adapters/file_write_execute_adapter.py`
- `examples/adapters/openai_compatible_plan_adapter.py`

The OpenAI-compatible plan adapter supports:
- `AXIOM_OPENAI_COMPAT_BASE_URL`
- `AXIOM_OPENAI_COMPAT_MODEL`
- `AXIOM_OPENAI_COMPAT_API_KEY`
- `AXIOM_OPENAI_COMPAT_TIMEOUT`
- `AXIOM_OPENAI_COMPAT_RETRIES`
- `AXIOM_OPENAI_COMPAT_RETRY_DELAY`

Still deferred:
- built-in vendor-specific model adapters
- production-grade local model server clients beyond the reference OpenAI-compatible shim
- long-running agent sessions
- streaming adapter output
- automatic approval of escalated tools
