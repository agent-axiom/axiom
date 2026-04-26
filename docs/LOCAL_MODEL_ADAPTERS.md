# Local Model Adapter Flow

AXIOM does not embed a coding agent. It invokes explicit local command adapters that speak `axiom.adapter.v1` JSON over stdin/stdout.

The smallest useful local-model flow is:

1. `run plan --adapter-command ...openai_compatible_plan_adapter.py`
2. human or host agent applies/records execution
3. `run verify` with real checks and manual smoke
4. `run review --adapter-command ...openai_compatible_review_adapter.py`
5. deterministic gates still decide whether finish is allowed

## Ollama-Compatible Example

If your local server exposes OpenAI-compatible `/v1/chat/completions`:

```bash
export AXIOM_OPENAI_COMPAT_BASE_URL=http://localhost:11434/v1
export AXIOM_OPENAI_COMPAT_MODEL=qwen2.5-coder

bin/axiom --repo-root "$(pwd)" run plan "$TASK_ID" \
  --adapter-command "python3 examples/adapters/openai_compatible_plan_adapter.py"

bin/axiom --repo-root "$(pwd)" run review "$TASK_ID" \
  --adapter-command "python3 examples/adapters/openai_compatible_review_adapter.py"
```

## vLLM Or Internal Gateway Example

```bash
export AXIOM_OPENAI_COMPAT_BASE_URL=http://localhost:8000/v1
export AXIOM_OPENAI_COMPAT_MODEL=local-coder
export AXIOM_OPENAI_COMPAT_API_KEY="$INTERNAL_TOKEN"

bin/axiom --repo-root "$(pwd)" run plan "$TASK_ID" \
  --adapter-command "python3 /opt/axiom-adapters/openai_compatible_plan_adapter.py"
```

## Failure Semantics

The reference adapters fail closed:
- HTTP errors produce non-zero adapter exits.
- invalid model JSON is retried with `AXIOM_OPENAI_COMPAT_SCHEMA_RETRIES`.
- missing required response keys are treated as invalid model JSON.
- AXIOM persists adapter failures as phase artifacts.

These adapters are examples, not sandboxes. They run as the current OS user in the task worktree.
