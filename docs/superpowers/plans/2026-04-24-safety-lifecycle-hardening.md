# Safety and Lifecycle Hardening

**Goal:** Make AXIOM's lifecycle enforcement and execution safety as strict as the finish gate.

**Architecture:** Keep AXIOM stdlib-only and local-first. Enforce state transitions before every phase, record forced or blocked decisions as persisted artifacts, diff task worktrees against immutable `base_commit`, bound verification command execution, persist adapter failures as phase artifacts, make degraded isolation explicit, and expose minimal worktree lifecycle commands.

**Tech Stack:** Python 3 standard library, `argparse`, `json`, `subprocess`, `unittest`, git worktrees

### Task 1: Phase transition enforcement

Files:
- Modify: `src/axiom/phases.py`
- Modify: `src/axiom/cli.py`
- Test: `tests/unit/test_phases.py`
- Test: `tests/unit/test_cli_bootstrap.py`

Steps:
- [x] Write tests proving phases cannot skip the state machine.
- [x] Add `--force` to phase CLI commands.
- [x] Persist blocked and forced transition decisions as artifacts.
- [x] Thread `force` through phase handlers without weakening default behavior.

### Task 2: Immutable base commit diffs

Files:
- Modify: `src/axiom/git.py`
- Modify: `src/axiom/models.py`
- Modify: `src/axiom/templates.py`
- Modify: `src/axiom/task_file.py`
- Modify: `schemas/task-frontmatter.schema.json`
- Test: `tests/unit/test_git_runtime.py`

Steps:
- [x] Record `base_commit` at task creation when HEAD exists.
- [x] Record `isolation_mode` as `worktree` or `degraded`.
- [x] Make task-scoped diff and changed files compare against `base_commit`.
- [x] Keep `base_branch` as human context only.

### Task 3: Bounded verification execution

Files:
- Modify: `src/axiom/tool_broker.py`
- Modify: `src/axiom/phases.py`
- Modify: `src/axiom/cli.py`
- Modify: `schemas/verify.schema.json`
- Test: `tests/unit/test_phases.py`

Steps:
- [x] Add default command timeout and output cap constants.
- [x] Capture timeout receipts with `exit_code=-1`.
- [x] Truncate stdout/stderr in persisted receipts.
- [x] Expose optional verify CLI flags for timeout and output cap.

### Task 4: Adapter trust and failure artifacts

Files:
- Modify: `src/axiom/adapters.py`
- Modify: `src/axiom/phases.py`
- Modify: `src/axiom/schema.py`
- Modify: `schemas/adapter-request.schema.json`
- Modify: `docs/ADAPTER_PROTOCOL.md`
- Modify: `adapters/README.md`
- Test: `tests/unit/test_adapters.py`

Steps:
- [x] Validate adapter requests before invocation.
- [x] Persist non-zero, invalid JSON, policy-blocked, and timeout adapter attempts.
- [x] Make command adapters explicitly trusted local commands, not sandboxes.
- [x] Remove unsupported review adapter phase from the v1 schema.

### Task 5: Phase artifact schema coverage

Files:
- Add: `schemas/design.schema.json`
- Add: `schemas/execute.schema.json`
- Add: `schemas/finish.schema.json`
- Test: `tests/unit/test_policy_schema.py`

Steps:
- [x] Add schemas for every persisted phase result.
- [x] Keep schema validation in the phase write path.
- [x] Add `const` support to the built-in validator for adapter protocol checks.

### Task 6: Degraded mode and worktree lifecycle UX

Files:
- Modify: `src/axiom/git.py`
- Modify: `src/axiom/phases.py`
- Modify: `src/axiom/cli.py`
- Modify: `README.md`
- Test: `tests/unit/test_git_runtime.py`
- Test: `tests/unit/test_cli_commands.py`

Steps:
- [x] Block degraded-mode review without manual evidence.
- [x] Add `axiom worktree list`.
- [x] Add `axiom worktree path <task>`.
- [x] Add guarded `axiom cleanup <task> --force`.

### Task 7: Reference local model shim

Files:
- Add: `examples/adapters/openai_compatible_plan_adapter.py`
- Modify: `docs/ADAPTER_PROTOCOL.md`
- Modify: `adapters/README.md`
- Test: `tests/unit/test_adapters.py`

Steps:
- [x] Add a small OpenAI-compatible plan adapter using only stdlib HTTP.
- [x] Keep it explicitly optional and local-endpoint friendly.
- [x] Do not add provider dependencies or autonomous editing behavior.

### Verification

- [x] Run focused unit tests after each major change.
- [x] Run `make test`.
- [x] Run a CLI smoke over a real git repo if unit tests expose gaps.
