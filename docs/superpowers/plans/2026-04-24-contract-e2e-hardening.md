# AXIOM Contract And E2E Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AXIOM's adapter, policy, review, and CLI lifecycle guarantees explicit, tested, and documented.

**Architecture:** Keep AXIOM stdlib-only and local-first. Strengthen review artifacts from heuristic findings into contract evidence, scope approvals by command/repo/task/worktree, publish `axiom.adapter.v1` as a stable spec with reference adapters, and add one CLI-level e2e test that exercises the adapter-backed workflow end to end.

**Tech Stack:** Python 3 standard library, `argparse`, `json`, `subprocess`, `unittest`, git worktrees

---

### Task 1: Contract-aware review evidence

**Files:**
- Modify: `src/axiom/phases.py`
- Modify: `tests/unit/test_phases.py`
- Modify: `schemas/review.schema.json`

- [ ] Add explicit review artifact fields: `planned_scope`, `actual_scope`, and `scope_mismatches`.
- [ ] Treat a git task with changed files and no plan write scope as `changes_requested`.
- [ ] Keep existing no-diff, docs, conflict-marker, and unfinished-marker checks.

### Task 2: Scoped approvals

**Files:**
- Modify: `src/axiom/approvals.py`
- Modify: `src/axiom/tool_broker.py`
- Modify: `src/axiom/models.py`
- Modify: `src/axiom/phases.py`
- Modify: `tests/unit/test_policy_schema.py`

- [ ] Store approval scope as command, repo root, optional task id, and optional worktree.
- [ ] Preserve repo-level approvals for CLI/manual use.
- [ ] Add receipt fields for `approval_reason` and `approval_scope`.
- [ ] Test blocked-before-approval and executed-after-approval in one flow.

### Task 3: Adapter protocol spec and reference adapters

**Files:**
- Create: `schemas/adapter-request.schema.json`
- Create: `docs/ADAPTER_PROTOCOL.md`
- Create: `examples/adapters/static_plan_adapter.py`
- Create: `examples/adapters/file_write_execute_adapter.py`
- Modify: `adapters/README.md`
- Test: `tests/unit/test_adapters.py`

- [ ] Document request and response contracts for `plan` and `execute`.
- [ ] Add two small reference adapters that are usable in tests and examples.
- [ ] Validate adapter request schema shape in tests.

### Task 4: CLI e2e workflow

**Files:**
- Modify: `tests/unit/test_cli_commands.py`

- [ ] Add one integration-style CLI test: `make -> design -> plan --adapter-command -> execute --adapter-command -> verify -> review -> finish`.
- [ ] Use a real git repo and real task worktree.
- [ ] Assert the task finishes and review artifact contains matching planned/actual scope.

### Task 5: Final verification and publish

**Files:**
- All modified runtime, schema, docs, examples, and tests.

- [ ] Run focused tests.
- [ ] Run `make test`.
- [ ] Run `git diff --check`.
- [ ] Commit and push `codex-contract-e2e-hardening`.
- [ ] Fast-forward `origin/main` if the branch is cleanly ahead.
