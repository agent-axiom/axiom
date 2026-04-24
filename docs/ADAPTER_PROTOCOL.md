# AXIOM Adapter Protocol

AXIOM adapters are local commands that speak JSON over stdin/stdout.

Adapters are trusted local commands, not sandboxes. AXIOM runs them as the current OS user in the task worktree. A plan adapter should only return JSON. An execute adapter may edit files in the task worktree. Do not point `--adapter-command` at untrusted scripts.

Protocol:

```text
axiom.adapter.v1
```

AXIOM invokes adapters explicitly through:

```bash
axiom run plan <task> --adapter-command "python3 adapter.py"
axiom run execute <task> --adapter-command "python3 adapter.py"
```

Adapters run in the task worktree. They must not assume the source checkout is the active workspace.

Optional local trust guardrails:
- `AXIOM_ADAPTER_ALLOWLIST`: path-separated list of allowed adapter script or executable paths
- `AXIOM_ADAPTER_SHA256`: path-separated `absolute_path=sha256` pins for adapter files

## Request

Every adapter receives one JSON object on stdin matching `schemas/adapter-request.schema.json`.

Important fields:
- `protocol`: always `axiom.adapter.v1`
- `phase`: `plan` or `execute`
- `task`: task metadata
- `task_path`: markdown task file path
- `repo_root`: target repository root
- `workspace`: isolated task worktree
- `base_branch`: human-readable base branch context
- `base_commit`: immutable git SHA used for task diffs when available
- `isolation_mode`: `worktree` or `degraded`
- `sections`: task file sections
- `latest_artifacts`: latest phase artifacts AXIOM chose to include
- `diff`: task-scoped diff, when relevant

## Plan Response

For `phase=plan`, return a JSON object matching `schemas/plan.schema.json`.

Example:

```json
{
  "summary": "Plan edits app.py only.",
  "steps": [
    {
      "id": "step-1",
      "title": "Apply the change in app.py.",
      "write_scope": ["app.py"],
      "checks": ["python3 -m unittest discover -s tests -v"]
    }
  ],
  "manual_smoke": [
    {
      "id": "smoke-1",
      "instruction": "Run the changed path manually and record observed output."
    }
  ],
  "stop_conditions": ["Stop if files outside app.py must change."]
}
```

## Execute Response

For `phase=execute`, the adapter may edit files inside `workspace` and should return:

```json
{
  "summary": "Applied the requested change."
}
```

AXIOM records:
- adapter receipt
- changed files before execution
- changed files after execution
- newly changed files

## Failure Handling

AXIOM persists failed adapter attempts as phase artifacts instead of dropping the error into transient CLI output only.

Persisted failure cases include:
- adapter command blocked by policy or adapter trust guardrails
- non-zero adapter exit
- adapter timeout
- stdout that is not a JSON object

For `plan`, a failed adapter attempt records a `plan` artifact with `outcome=blocked` and leaves the task in `plan.blocked`.

For `execute`, a failed adapter attempt records an `execute` artifact with `outcome=failed`, the pre/post changed-file evidence AXIOM can observe, and leaves the task in `execute.failed`.

## Reference Adapters

See:
- `examples/adapters/static_plan_adapter.py`
- `examples/adapters/file_write_execute_adapter.py`
- `examples/adapters/openai_compatible_plan_adapter.py`

The static and file-write adapters are intentionally simple shims for local testing and closed-infra bootstrapping. The OpenAI-compatible plan adapter is a small reference client for local `/v1/chat/completions` servers such as an internal gateway or local model server.
