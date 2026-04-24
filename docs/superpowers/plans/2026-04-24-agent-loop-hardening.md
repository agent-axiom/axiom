# AXIOM Agent Loop Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move AXIOM from a task-isolated recorder toward a usable local-agent workflow runtime without adding vendor lock-in or unsafe autonomy.

**Architecture:** Add a stdlib-only command adapter protocol that can call a local model shim or host coding agent through JSON over stdin/stdout. Keep deterministic fallback behavior, but let `plan` and `execute` invoke an adapter when explicitly configured; improve review by comparing plan write scope to actual task-scoped diff; add persisted approval records for `escalate` policy decisions; make metadata flags control finish gates instead of being decorative.

**Tech Stack:** Python 3 standard library, `argparse`, `json`, `subprocess`, `hashlib`, `unittest`, git worktrees

---

### Task 1: Documentation synchronization

**Files:**
- Modify: `README.md`
- Modify: `adapters/README.md`

- [ ] Replace stale bootstrap limitations that claim AXIOM lacks real worktree provisioning.
- [ ] Document the current command-adapter protocol and the remaining adapter limitations.
- [ ] Keep installation guidance source-first and closed-infra friendly.

### Task 2: Command adapter protocol

**Files:**
- Create: `src/axiom/adapters.py`
- Modify: `src/axiom/cli.py`
- Modify: `src/axiom/phases.py`
- Test: `tests/unit/test_adapters.py`

- [ ] Write failing tests for adapter request shape and JSON response parsing.
- [ ] Add `axiom adapter list`.
- [ ] Add `--adapter-command` to `run plan` and `run execute`.
- [ ] Run focused adapter tests until green.

### Task 3: Execute as policy-controlled adapter loop

**Files:**
- Modify: `src/axiom/phases.py`
- Modify: `tests/unit/test_adapters.py`

- [ ] Write a failing test where an execute adapter edits a file in the task worktree.
- [ ] Record adapter receipt, pre/post changed files, and new changed files in the execute artifact.
- [ ] Keep plain `run execute --note` as a deterministic recorder fallback.

### Task 4: Review stronger than simple diff heuristics

**Files:**
- Modify: `src/axiom/phases.py`
- Modify: `tests/unit/test_phases.py`

- [ ] Write a failing test where plan write scope says `app.py`, actual diff changes `README.md`, and review returns `changes_requested`.
- [ ] Keep no-diff, docs, conflict-marker, and unfinished-marker findings.
- [ ] Record plan write scope and changed files in review artifact.

### Task 5: Policy approval flow

**Files:**
- Create: `src/axiom/approvals.py`
- Modify: `src/axiom/tool_broker.py`
- Modify: `src/axiom/cli.py`
- Modify: `tests/unit/test_policy_schema.py`

- [ ] Write a failing test proving an `escalate` command is blocked before approval.
- [ ] Write a failing test proving the same command runs after persisted approval.
- [ ] Add `axiom policy approve --command ... --reason ...` and `axiom policy approvals`.

### Task 6: Metadata flags with real semantics

**Files:**
- Modify: `src/axiom/state_machine.py`
- Modify: `src/axiom/phases.py`
- Modify: `tests/unit/test_state_machine.py`
- Modify: `tests/unit/test_phases.py`

- [ ] Write failing tests for `verification_required=false` and `review_required=false`.
- [ ] Allow `finish` from the correct earlier status only when the corresponding gate is explicitly disabled.
- [ ] Keep verification, review, manual smoke, and docs mandatory by default.

### Task 7: Final verification and publish

**Files:**
- All modified runtime, docs, and tests.

- [ ] Run focused adapter/policy/phase tests.
- [ ] Run `make test`.
- [ ] Run CLI smoke for command adapter plan/execute.
- [ ] Commit and push `codex-agent-loop-hardening`.
- [ ] Fast-forward `origin/main` only if the branch is cleanly ahead of `origin/main`.
