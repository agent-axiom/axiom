# AXIOM Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn AXIOM's bootstrap runtime into a real task-isolated workflow engine slice.

**Architecture:** Provision a git worktree per task when the target repo has a valid HEAD, keep non-git and no-HEAD repos as explicit bootstrap fallbacks, and make all diff/execute/verify/review behavior read from the task workspace rather than repo-wide state. Add small stdlib-only schema and policy modules so phase artifacts are runtime-validated and verification commands pass through an auditable broker.

**Tech Stack:** Python 3 standard library, `argparse`, `subprocess`, `json`, `unittest`, git worktrees

---

### Task 1: Git-backed isolation tests

**Files:**
- Create: `tests/unit/test_git_runtime.py`
- Modify: `src/axiom/git.py`
- Modify: `src/axiom/task_file.py`

- [ ] Write a failing test that creates a git repo with an initial commit, makes a task, and asserts the task worktree exists outside the repo root on the declared branch.
- [ ] Write a failing test that creates a git repo without an initial commit and asserts AXIOM falls back to the repo root with a recorded assumption.
- [ ] Implement worktree provisioning and local exclude protection.
- [ ] Run `python3 -m unittest tests.unit.test_git_runtime -v` until green.

### Task 2: Task-scoped change tracking

**Files:**
- Modify: `tests/unit/test_git_runtime.py`
- Modify: `src/axiom/git.py`
- Modify: `src/axiom/cli.py`
- Modify: `src/axiom/phases.py`

- [ ] Write a failing test proving `axiom diff <task>` reads the task worktree diff, not unrelated dirty files in the source checkout.
- [ ] Write a failing test proving `run_execute()` records changed files from the task worktree only.
- [ ] Implement task-scoped diff and changed-file helpers.
- [ ] Run the focused git runtime tests until green.

### Task 3: Schema and policy guardrails

**Files:**
- Create: `src/axiom/schema.py`
- Create: `src/axiom/policy.py`
- Create: `src/axiom/tool_broker.py`
- Modify: `src/axiom/models.py`
- Modify: `src/axiom/phases.py`
- Modify: `schemas/verify.schema.json`
- Create: `tests/unit/test_policy_schema.py`

- [ ] Write failing tests for schema rejection of malformed phase payloads.
- [ ] Write failing tests proving dangerous verification commands are blocked before execution.
- [ ] Implement minimal JSON-schema enforcement for AXIOM's schemas.
- [ ] Implement allow/deny/escalate command policy and route verification commands through the Tool Broker.
- [ ] Run policy/schema tests until green.

### Task 4: Operational plan and real review gate

**Files:**
- Modify: `src/axiom/phases.py`
- Modify: `tests/unit/test_phases.py`

- [ ] Write failing tests proving `run_plan()` uses repo anchors and discovered checks instead of a generic placeholder.
- [ ] Write failing tests proving `run_review()` can return `changes_requested` when verification passed but the task diff/docs evidence is insufficient.
- [ ] Implement deterministic plan generation from task anchors, scope, checks, and manual smoke requirements.
- [ ] Implement diff-aware deterministic review findings with `blocked`, `changes_requested`, and `pass` outcomes.
- [ ] Run phase tests until green.

### Task 5: Full verification and publish

**Files:**
- All modified runtime, schema, docs, and tests.

- [ ] Run `make test`.
- [ ] Run a CLI smoke test that makes a task in a real git repo and shows its isolated worktree.
- [ ] Inspect `git diff --stat`.
- [ ] Commit the runtime hardening slice.
- [ ] Push `codex-runtime-hardening`.
