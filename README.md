# AXIOM

AXIOM is a local-first workflow layer for coding agents. This bootstrap slice implements a deterministic CLI around one markdown task file per task, persisted phase artifacts, hard completion gates for verification and review, and a source-first release transparency model built on GitHub Releases and GitHub Actions.

AXIOM is not a prompt pack and not a giant autonomous IDE. The core idea is that the workflow lives in local files and a deterministic CLI, not in chat history.

## Bootstrap Scope

This first slice includes:
- one markdown task file per task under `.axiom/tasks/`
- first-class git worktree provisioning for git repositories with an initial commit
- immutable `base_commit` tracking for task-scoped diffs
- structured JSON artifacts under `.axiom/artifacts/shared/`
- a lifecycle CLI with `make`, `resume`, `list`, `show`, `diff`, `run <phase>`, `finish`, `adapter`, `policy`, `worktree`, `cleanup`, `doctor`, and `version`
- an explicit command-adapter protocol for local model shims and host coding agents
- mandatory verification and review gates before completion
- release metadata files and GitHub Actions workflows for transparent releases

This slice is intentionally deterministic and stdlib-only. It can run without an LLM, but it now has a real command-adapter seam for local models and host agents that speak JSON over stdin/stdout.

Runtime schemas are packaged inside the Python package and loaded through package resources. The top-level `schemas/` directory remains the human-readable contract source in the repository; tests ensure packaged copies stay in sync.

## What The Binary Actually Does

The `axiom` binary is a local workflow engine.

It does not just route between prompt files. Its job is to enforce workflow discipline around an agent or model:
- create and update one markdown task file per task
- provision an isolated git worktree per task when the target repository supports it
- enforce task status transitions
- record blocked or forced lifecycle overrides as decision artifacts
- persist phase artifacts under `.axiom/artifacts/`
- optionally call a local command adapter for planning and execution
- gate completion on verify and review
- keep work portable across different agent hosts

In other words:
- prompts are optional implementation detail
- the CLI is the control plane
- the task file is the source of truth

## How A User Actually Runs This

There are two layers:

- AXIOM runtime:
  the local `axiom` CLI, installed once in the environment
- Project state:
  the `.axiom/` directory inside the target repository

The intended operational model is:
- platform or infra team makes `axiom` available inside the closed environment
- user or local agent runs `axiom` against a target project
- AXIOM writes task files and artifacts into that target project

The end user should not need to clone AXIOM into every repository by hand.

## Short Answer: Do I Need To Clone This Repo?

Today, with the current bootstrap implementation, the answer is:

- yes, AXIOM must exist locally somewhere at least once
- no, it does not need to be copied into every target project

The current bootstrap workflow is:
- clone AXIOM once as a local tool repository, or make it available centrally
- point AXIOM at a target repository with `--repo-root`
- let AXIOM create `.axiom/` inside that target repository

Practical example:

```bash
git clone <internal-axiom-repo> ~/tools/axiom
~/tools/axiom/bin/axiom --repo-root /repos/payments make "fix retry logic"
```

In a more polished v1, the preferred user experience is:

```bash
axiom --repo-root /repos/payments make "fix retry logic"
```

## Closed Infrastructure Model

In a closed or air-gapped environment, the recommended setup is:

1. Make AXIOM available locally:
   as an internal binary, internal package, internal mirror, or vendored tool directory
2. Open the target project repository
3. Run AXIOM against that repository
4. Let AXIOM create `.axiom/tasks/...` and `.axiom/artifacts/...` inside the target repository

This means AXIOM behaves like a local toolchain component, not like a cloud service.

## Three Deployment Modes

### 1. Central Install

Best default for closed infrastructure.

- install `axiom` once on developer workstations, VMs, or jump hosts
- expose it in `PATH`
- run it against any local repository

Example:

```bash
axiom --repo-root /repos/payments make "fix retry logic"
```

### 2. Internal Mirror Or Sidecar Repo

Good when the environment allows internal git access but not internet access.

- mirror the AXIOM repository internally
- clone it once somewhere like `/opt/axiom` or `/srv/tools/axiom`
- run its launcher against any project

Example:

```bash
/opt/axiom/bin/axiom --repo-root /repos/payments make "fix retry logic"
```

### 3. Vendored Into A Project

Good for highly locked-down or audit-heavy environments.

- copy AXIOM into `tools/axiom/` or a similar project-local directory
- run it from there
- keep workflow state in the project's `.axiom/` directory

This is heavier operationally, but simplest to audit in fully isolated environments.

## Ready Instructions For A Human

Use this when a person is setting up AXIOM manually in a closed environment for the current bootstrap version.

### Option A: Clone AXIOM Once, Then Use It Against A Project

```bash
git clone <internal-axiom-repo> ~/tools/axiom
cd ~/tools/axiom
make test

TASK_PATH=$(~/tools/axiom/bin/axiom --repo-root /repos/myproject make "fix invoice rounding")
TASK_ID=$(basename "$TASK_PATH" | sed -E 's/^(AX-[0-9]{8}-[0-9]{3})-.*$/\1/')

~/tools/axiom/bin/axiom --repo-root /repos/myproject list
~/tools/axiom/bin/axiom --repo-root /repos/myproject run design "$TASK_ID"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run plan "$TASK_ID"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run execute "$TASK_ID" --note "Applied implementation changes"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run verify "$TASK_ID" --check "python3 -m unittest discover -s tests/unit -v" --manual-smoke "smoke-1:passed:Observed expected runtime behavior"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run review "$TASK_ID"
~/tools/axiom/bin/axiom --repo-root /repos/myproject finish "$TASK_ID"
```

Result:
- AXIOM stays in `~/tools/axiom`
- workflow state for the actual work is written into `/repos/myproject/.axiom/`

### Option B: Use A Centrally Installed AXIOM Binary

If your platform team already installed AXIOM into `PATH`, the workflow becomes:

```bash
TASK_PATH=$(axiom --repo-root /repos/myproject make "fix invoice rounding")
TASK_ID=$(basename "$TASK_PATH" | sed -E 's/^(AX-[0-9]{8}-[0-9]{3})-.*$/\1/')

axiom --repo-root /repos/myproject list
axiom --repo-root /repos/myproject run design "$TASK_ID"
axiom --repo-root /repos/myproject run plan "$TASK_ID"
axiom --repo-root /repos/myproject run execute "$TASK_ID" --note "Applied implementation changes"
axiom --repo-root /repos/myproject run verify "$TASK_ID" --check "python3 -m unittest discover -s tests/unit -v" --manual-smoke "smoke-1:passed:Observed expected runtime behavior"
axiom --repo-root /repos/myproject run review "$TASK_ID"
axiom --repo-root /repos/myproject finish "$TASK_ID"
```

## Ready Instructions For A Local Agent

Use this when the user wants a local coding agent to operate through AXIOM instead of editing the project ad hoc.

### Agent Prompt: AXIOM Already Installed

Copy-paste instruction for the agent:

> Work on repository `/repos/myproject` through AXIOM only. Use `axiom --repo-root /repos/myproject ...` for task creation and phase transitions. Create a task named `fix invoice rounding`, then drive it through `design`, `plan`, `execute`, `verify`, `review`, and `finish`. Keep all persisted state in the project's `.axiom/` directory and do not rely on chat history as the source of truth.

### Agent Prompt: AXIOM Not Installed Yet

Copy-paste instruction for the agent:

> If AXIOM is not already present locally, clone the internal AXIOM repository into `/opt/axiom`. After that, work on repository `/repos/myproject` through `/opt/axiom/bin/axiom --repo-root /repos/myproject ...`. Create a task named `fix invoice rounding`, then drive it through `design`, `plan`, `execute`, `verify`, `review`, and `finish`. Persist workflow state in `/repos/myproject/.axiom/`.

### Agent Prompt: Vendored AXIOM Inside The Project

Copy-paste instruction for the agent:

> Use the vendored AXIOM runtime at `/repos/myproject/tools/axiom/bin/axiom`. Run all workflow actions against repository `/repos/myproject` with `--repo-root /repos/myproject`. Create a task named `fix invoice rounding`, then drive it through `design`, `plan`, `execute`, `verify`, `review`, and `finish`. Keep the task file authoritative.

## Usage Scenarios

These are the main scenarios users should think in.

### Scenario 1: One Developer, One Closed Repository

Best fit:
- clone AXIOM once into a local tools directory
- run `bin/axiom --repo-root /path/to/project ...`

Why:
- simplest setup
- no packaging work required
- easy to inspect and modify

### Scenario 2: Internal Platform Team Supports Many Repositories

Best fit:
- install AXIOM once as an internal binary or package
- expose `axiom` in `PATH`

Why:
- lowest friction for end users
- consistent versioning
- easiest to standardize across teams

### Scenario 3: Local Coding Agent Works Across Multiple Projects

Best fit:
- keep AXIOM installed centrally or in `/opt/axiom`
- give the agent a fixed instruction to always operate through `axiom --repo-root <project>`

Why:
- the agent can switch projects without re-installing AXIOM
- state stays with each project in `.axiom/`
- workflow survives host or agent restarts

### Scenario 4: Fully Air-Gapped Or Audit-Heavy Repository

Best fit:
- vendor AXIOM into the project under `tools/axiom/`

Why:
- everything needed lives with the repository
- easiest to audit
- no dependency on external install location

Tradeoff:
- heavier upgrades
- more per-repo maintenance

## Release Transparency And Verification

AXIOM release transparency is source-first and built on GitHub Releases plus GitHub Actions.

### What A Release Publishes

Each tagged release is expected to publish:
- wheel
- source distribution
- `SHA256SUMS`
- `SBOM.spdx.json`

The release workflow also emits GitHub artifact attestations for the release assets and the SBOM.

### Inspect Local Build Metadata

Use:

```bash
bin/axiom version --verbose
```

This prints:
- `version`
- `git_commit`
- `git_tag`
- `build_timestamp`
- `source_repo`

### Verify A Release Asset

Basic verification:

```bash
shasum -a 256 ./axiom_workflow-0.1.0-py3-none-any.whl
cat SHA256SUMS
```

Provenance verification with GitHub CLI:

```bash
gh attestation verify ./axiom_workflow-0.1.0-py3-none-any.whl \
  --repo agent-axiom/axiom \
  --signer-workflow agent-axiom/axiom/.github/workflows/release.yml \
  --source-ref refs/tags/v0.1.0
```

If immutable releases are enabled for the repository, GitHub also supports release verification flows:

```bash
gh release verify v0.1.0 --repo agent-axiom/axiom
gh release verify-asset v0.1.0 ./axiom_workflow-0.1.0-py3-none-any.whl --repo agent-axiom/axiom
```

See [RELEASE.md](RELEASE.md) for the full publication and verification flow.

## Quick Start

```bash
TASK_PATH=$(bin/axiom --repo-root "$(pwd)" make "Add verify gate")
TASK_ID=$(basename "$TASK_PATH" | sed -E 's/^(AX-[0-9]{8}-[0-9]{3})-.*$/\1/')

bin/axiom --repo-root "$(pwd)" list
bin/axiom --repo-root "$(pwd)" run design "$TASK_ID"
bin/axiom --repo-root "$(pwd)" run plan "$TASK_ID"
bin/axiom --repo-root "$(pwd)" run execute "$TASK_ID" --note "Applied code changes"
bin/axiom --repo-root "$(pwd)" run verify "$TASK_ID" --check "python3 -m unittest discover -s tests/unit -v" --manual-smoke "smoke-1:passed:Observed expected behavior"
bin/axiom --repo-root "$(pwd)" run review "$TASK_ID"
bin/axiom --repo-root "$(pwd)" finish "$TASK_ID"
bin/axiom --repo-root "$(pwd)" worktree path "$TASK_ID"
bin/axiom --repo-root "$(pwd)" doctor
bin/axiom version --verbose
```

For local development, `bin/axiom` sets `PYTHONPATH=src` so the CLI works without installing the package first.

## Adapter And Policy Notes

Adapter protocol:
- Spec: [docs/ADAPTER_PROTOCOL.md](docs/ADAPTER_PROTOCOL.md)
- Reference plan adapter: `examples/adapters/static_plan_adapter.py`
- Reference execute adapter: `examples/adapters/file_write_execute_adapter.py`
- Reference OpenAI-compatible plan shim: `examples/adapters/openai_compatible_plan_adapter.py`

Command adapters are trusted local commands. AXIOM does not sandbox them. They run in the task worktree and can read or write files available to the current OS user. Use them only from trusted internal paths. Optional guardrails are available through:
- `AXIOM_ADAPTER_ALLOWLIST`: path-separated list of allowed adapter script or executable paths
- `AXIOM_ADAPTER_SHA256`: path-separated `absolute_path=sha256` pins for adapter files

Policy approvals are explicit and local. Escalated commands are blocked until approved:

```bash
bin/axiom --repo-root "$(pwd)" policy approve \
  --task "$TASK_ID" \
  --command "git push --dry-run" \
  --reason "human reviewed this dry-run push"

bin/axiom --repo-root "$(pwd)" policy approvals
```

Review is contract-aware for git tasks. The latest plan write scope is compared against the task-scoped changed files, and the review artifact records `planned_scope`, `actual_scope`, and `scope_mismatches`.

Optional review adapters are supported as an additional semantic review layer:

```bash
bin/axiom --repo-root "$(pwd)" run review "$TASK_ID" \
  --adapter-command "python3 /opt/axiom-adapters/local_reviewer.py"
```

The review adapter cannot bypass deterministic gates. If verification failed, docs are unresolved, no task diff exists, or changed files escape the planned write scope, AXIOM returns `changes_requested` or `blocked` before any semantic adapter can turn the review into a pass.

Verification commands are run through the tool broker with policy checks, timeouts, and stdout/stderr capture limits. Hung commands produce failed receipts with `exit_code=-1`.

The command policy is a guardrail, not a sandbox. It blocks known-dangerous direct commands and shell control operators, but it cannot prevent a trusted interpreter command from doing arbitrary work. For tighter environments, use strict mode:

```bash
bin/axiom --repo-root "$(pwd)" run verify "$TASK_ID" \
  --policy-profile strict \
  --check "python3 -m unittest discover -s tests/unit -v" \
  --manual-smoke "smoke-1:passed:Observed expected behavior"
```

Policy profiles:
- `standard`: default guardrails with escalation for dependency changes and sensitive git operations
- `strict`: only known test runners or commands passed through `--policy-allow`
- `permissive`: allows escalation-class commands but still denies destructive and shell-control patterns

## Current Bootstrap Limitation

This repository now proves the load-bearing local workflow and release transparency pieces first:
- task file lifecycle
- real git worktree provisioning for repositories with an initial commit
- task-scoped diff and changed-file tracking against immutable `base_commit`
- untracked new-file content in task diff evidence
- command-adapter protocol for local model shims and host agents
- persisted adapter failure artifacts
- strict phase transition enforcement with explicit `--force` override logging
- persisted artifacts
- verification and review gates
- self-contained installed-wheel smoke coverage in CI and release workflows
- deterministic local CLI control
- embedded build metadata
- GitHub Releases and GitHub Actions based release verification assets

It still does not ship:
- vendor-specific model adapters
- a built-in autonomous code-editing agent
- native local model server integrations beyond the small OpenAI-compatible reference plan shim
- reproducible builds
- native macOS signing or notarization

The current adapter support is deliberately narrow: AXIOM can invoke an explicit local command adapter for `run plan`, `run execute`, and optional semantic `run review`, passing a structured JSON request on stdin and reading JSON from stdout. This is enough to integrate a local model shim or a host-agent wrapper without making AXIOM depend on a single provider.

Example:

```bash
bin/axiom --repo-root "$(pwd)" run plan "$TASK_ID" \
  --adapter-command "python3 /opt/axiom-adapters/local_planner.py"

bin/axiom --repo-root "$(pwd)" run execute "$TASK_ID" \
  --adapter-command "python3 /opt/axiom-adapters/local_executor.py"

bin/axiom --repo-root "$(pwd)" run review "$TASK_ID" \
  --adapter-command "python3 /opt/axiom-adapters/local_reviewer.py"
```

Worktree lifecycle helpers:

```bash
bin/axiom --repo-root "$(pwd)" worktree list
bin/axiom --repo-root "$(pwd)" worktree path "$TASK_ID"
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --dry-run
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --force
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --only-if-done --force --delete-branch
```

Default cleanup removes only the managed worktree and keeps the task branch. `--delete-branch` uses safe `git branch -d`; unmerged branches are not force-deleted.

Runtime diagnostics:

```bash
bin/axiom --repo-root "$(pwd)" doctor
bin/axiom --repo-root "$(pwd)" doctor --json
```

`doctor` checks Python version, schema availability, git/HEAD/worktree readiness, write permissions, adapter trust environment, and policy profiles.

Non-git repositories and git repositories without an initial commit run in `isolation_mode: degraded`. In degraded mode, review requires manual smoke evidence before it can pass.

## Repository Layout

- `src/axiom/`: CLI and core workflow code
- `.axiom/tasks/`: markdown task files
- `.axiom/artifacts/shared/`: persisted phase outputs
- `scripts/`: release metadata generation helpers
- `examples/adapters/`: minimal command adapters for protocol testing
- `src/axiom/schemas/`: packaged runtime schemas
- `.github/workflows/`: test and release workflows
- `tests/unit/`: bootstrap verification suite
