# AXIOM Adapter Protocol

AXIOM adapters are local commands that speak JSON over stdin/stdout.

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

## Request

Every adapter receives one JSON object on stdin matching `schemas/adapter-request.schema.json`.

Important fields:
- `protocol`: always `axiom.adapter.v1`
- `phase`: `plan` or `execute`
- `task`: task metadata
- `task_path`: markdown task file path
- `repo_root`: target repository root
- `workspace`: isolated task worktree
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

## Reference Adapters

See:
- `examples/adapters/static_plan_adapter.py`
- `examples/adapters/file_write_execute_adapter.py`

These are intentionally simple shims for local testing and closed-infra bootstrapping. They are not model clients.
