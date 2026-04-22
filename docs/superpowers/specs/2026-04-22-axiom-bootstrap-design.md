# AXIOM Bootstrap Design

## Goal

Build the first end-to-end local AXIOM slice: a Python CLI that manages one markdown task file per task, persists artifacts per phase, enforces a task state machine, and requires verification and review before completion.

## Scope

In scope:
- Markdown task files with YAML-like frontmatter
- Deterministic CLI with `make`, `resume`, `list`, `show`, `diff`, `run <phase>`, and `finish`
- Phase artifacts for plan, execute, verify, and review
- Worktree-aware task metadata and bootstrap validation
- Hard gates for verification and review
- Manual smoke capture in verify
- Stdlib-only implementation

Out of scope for this slice:
- Real LLM or host-agent adapters
- Full policy DSL
- Semantic symbol indexing
- Multi-agent delegation
- Remote sync

## Decisions

### Language and runtime

Use Python 3 with the standard library only. This keeps the bootstrap slice easy to run in a blank repository and avoids package-manager coupling while the workflow model is still being proven.

### Task file as source of truth

Each task lives in `.axiom/tasks/YYYY/MM/<task-id>-<slug>.md`. The task file contains frontmatter, required workflow sections, and generated phase blocks between managed markers. Shared artifacts store structured results and receipts, but the task file is the authoritative operational summary.

### State machine

The CLI owns legal phase transitions. A task may not move forward unless the required sections and prior artifacts exist. `finish` may only succeed if verify passed, manual smoke is complete or waived, review passed, and docs impact has been resolved.

### Worktree model

AXIOM treats one task as one branch and one worktree. For this repository bootstrap only, development is happening in the primary checkout because the repo has no initial commit and git cannot create worktrees from an unborn branch. The product itself will still implement real worktree management.

### Structured phase artifacts

`plan`, `verify`, and `review` produce JSON files under `.axiom/artifacts/shared/<task-id>/<phase>/<attempt>/result.json`. The CLI renders concise summaries from those JSON artifacts into the markdown task file.

### Execution mode

This first slice uses deterministic local execution, not a model. `run plan`, `run execute`, `run verify`, and `run review` are driven by CLI logic and flags. The code will define adapter interfaces so future model-backed execution can plug in without changing workflow state.

### Safety

Keep operations explicit and local:
- argv-based subprocess execution only
- no background daemons
- no raw shell strings in the product code
- no writes outside the repo root
- no destructive git commands

## File Structure

- `src/axiom/cli.py`: argparse entrypoint and command wiring
- `src/axiom/config.py`: repository layout and path helpers
- `src/axiom/task_file.py`: markdown task parsing and rendering
- `src/axiom/state_machine.py`: statuses and legal transitions
- `src/axiom/artifacts.py`: artifact directories and JSON persistence
- `src/axiom/git.py`: git status, diff, branch, and worktree helpers
- `src/axiom/phases.py`: plan, execute, verify, review, and finish behavior
- `src/axiom/models.py`: dataclasses for task metadata and phase results
- `src/axiom/templates.py`: default task file template
- `tests/unit/...`: focused unit tests for lifecycle and gating behavior

## Verification Strategy

Verification for this slice is local and deterministic:
- unit tests for task parsing, state transitions, and lifecycle gates
- CLI integration tests for make -> plan -> execute -> verify -> review -> finish
- manual smoke capture is recorded inside task verify artifacts

## Risks

- Frontmatter parsing complexity without YAML dependency: mitigate with a constrained parser and tests
- Git behavior on empty repos: mitigate with explicit bootstrap detection and error messaging
- Phase command ambiguity without model assistance: mitigate by keeping the bootstrap commands explicit and file-based

## Success Criteria

The bootstrap slice is successful when a user can:
1. Create a task with one command.
2. Advance it through plan, execute, verify, and review with persisted artifacts.
3. Resume entirely from disk state.
4. Be blocked from completion until verify and review both pass.
