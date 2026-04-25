# Install and Evidence Hardening

**Goal:** Stabilize AXIOM's installed-wheel runtime, evidence capture, and command policy behavior before adding larger agent features.

**Architecture:** Package runtime schemas inside `axiom`, load them through `importlib.resources`, add installed-wheel smoke coverage to CI/release, capture untracked file content in task diffs, add command policy profiles, and remove misleading stale blocked metadata after successful forced phases.

**Tech Stack:** Python 3 standard library, setuptools package data, GitHub Actions, git, unittest

### Task 1: Installed schema runtime

Files:
- Modify: `src/axiom/schema.py`
- Modify: `pyproject.toml`
- Add: `src/axiom/schemas/*.json`
- Test: `tests/unit/test_packaging.py`

Steps:
- [x] Prove package schema resources are missing.
- [x] Load schemas via `importlib.resources`.
- [x] Add adapter-request fallback enforcement when files are unavailable.
- [x] Include schemas in wheel package data.

### Task 2: Installed wheel smoke

Files:
- Add: `scripts/installed_wheel_smoke.py`
- Modify: `.github/workflows/test.yml`
- Modify: `.github/workflows/release.yml`

Steps:
- [x] Build wheel.
- [x] Install wheel into a clean venv.
- [x] Run CLI smoke through installed `axiom`, not `PYTHONPATH=src`.
- [x] Add the same check to CI and release.

### Task 3: Untracked diff evidence

Files:
- Modify: `src/axiom/git.py`
- Test: `tests/unit/test_git_runtime.py`

Steps:
- [x] Prove untracked file content is missing from task diff.
- [x] Append `git diff --no-index /dev/null <file>` evidence for untracked files.
- [x] Keep changed-file tracking behavior unchanged.

### Task 4: Command policy profiles

Files:
- Modify: `src/axiom/policy.py`
- Modify: `src/axiom/tool_broker.py`
- Modify: `src/axiom/phases.py`
- Modify: `src/axiom/cli.py`
- Test: `tests/unit/test_policy_schema.py`
- Test: `tests/unit/test_cli_bootstrap.py`

Steps:
- [x] Add `standard`, `strict`, and `permissive` profiles.
- [x] Make `strict` allow only known test runners or explicit allowlist entries.
- [x] Keep destructive operations denied in every profile.
- [x] Expose `--policy-profile` and `--policy-allow` for verify.

### Task 5: Forced transition metadata

Files:
- Modify: `src/axiom/phases.py`
- Test: `tests/unit/test_phases.py`

Steps:
- [x] Prove stale `blocked_reason` can survive a forced successful phase.
- [x] Clear `blocked_reason` after successful design/plan/execute phases.
- [x] Keep decision artifacts as the audit trail.

### Verification

- [x] Focused failing tests before implementation.
- [x] `make test`
- [x] `python3 -m build --wheel`
- [x] clean venv install smoke through built wheel
