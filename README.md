# AXIOM

AXIOM is a local-first workflow layer for coding agents. This bootstrap slice
implements a deterministic CLI around one markdown task file per task,
persisted phase artifacts, hard completion gates for verification and review,
and a source-first release transparency model built on GitHub Releases and
GitHub Actions.

AXIOM is not a prompt pack and not a giant autonomous IDE. The core idea is
that the workflow lives in local files and a deterministic CLI, not in chat
history.

## Bootstrap Scope

This first slice includes:
- one markdown task file per task under `.axiom/tasks/`
- first-class git worktree provisioning for git repositories with an initial commit
- immutable `base_commit` tracking for task-scoped diffs
- structured JSON artifacts under `.axiom/artifacts/shared/`
- a lifecycle CLI with `make`, `resume`, `list`, `show`, `diff`,
  `run <phase>`, `finish`, `adapter`, `policy`, `worktree`, `cleanup`,
  `doctor`, and `version`
- an explicit command-adapter protocol for local model shims and host coding agents
- mandatory verification and review gates before completion
- release metadata files and GitHub Actions workflows for transparent releases

This slice is intentionally deterministic and stdlib-only. It can run without
an LLM, but it now has a real command-adapter seam for local models and host
agents that speak JSON over stdin/stdout.

Runtime schemas are packaged inside the Python package and loaded through
package resources. The top-level `schemas/` directory remains the human-readable
contract source in the repository; tests ensure packaged copies stay in sync.

## What The Binary Actually Does

The `axiom` binary is a local workflow engine.

It does not just route between prompt files. Its job is to enforce workflow
discipline around an agent or model:
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

## Installation And Deployment

AXIOM is installed once as a local tool and then pointed at target repositories
with `--repo-root`. It writes task files, artifacts, and policy state into the
target repository's `.axiom/` directory.

Common deployment modes:
- central install in `PATH`
- internal mirror or sidecar repo such as `/opt/axiom`
- vendored project-local tool under `tools/axiom/`

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for closed-infra setup, human
operator commands, local-agent prompts, and usage scenarios.

## Release Transparency

Release transparency is source-first and built on GitHub Releases plus GitHub
Actions. A tagged release is expected to publish a wheel, source distribution,
`SHA256SUMS`, `SBOM.spdx.json`, and GitHub artifact attestations.

There are currently no public release assets until the first tag is published.
See [RELEASE.md](RELEASE.md) for the publication and verification flow.

## Quick Start

```bash
TASK_PATH=$(bin/axiom --repo-root "$(pwd)" make "Add verify gate")
TASK_ID=$(basename "$TASK_PATH" | sed -E 's/^(AX-[0-9]{8}-[0-9]{3})-.*$/\1/')

bin/axiom --repo-root "$(pwd)" list
bin/axiom --repo-root "$(pwd)" run design "$TASK_ID"
bin/axiom --repo-root "$(pwd)" run plan "$TASK_ID"
bin/axiom --repo-root "$(pwd)" run execute "$TASK_ID" --note "Applied code changes"
bin/axiom --repo-root "$(pwd)" run verify "$TASK_ID" \
  --check "python3 -m unittest discover -s tests/unit -v" \
  --manual-smoke "smoke-1:passed:Observed expected behavior"
bin/axiom --repo-root "$(pwd)" run review "$TASK_ID"
bin/axiom --repo-root "$(pwd)" finish "$TASK_ID"
bin/axiom --repo-root "$(pwd)" worktree path "$TASK_ID"
bin/axiom --repo-root "$(pwd)" doctor
bin/axiom version --verbose
```

For local development, `bin/axiom` sets `PYTHONPATH=src` so the CLI works
without installing the package first.

## Adapter And Policy Notes

Adapter protocol:
- Spec: [docs/ADAPTER_PROTOCOL.md](docs/ADAPTER_PROTOCOL.md)
- Local model flow: [docs/LOCAL_MODEL_ADAPTERS.md](docs/LOCAL_MODEL_ADAPTERS.md)
- Demo walkthrough: [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md)
- Reference plan adapter: `examples/adapters/static_plan_adapter.py`
- Reference execute adapter: `examples/adapters/file_write_execute_adapter.py`
- Reference OpenAI-compatible plan shim: `examples/adapters/openai_compatible_plan_adapter.py`
- Reference OpenAI-compatible review shim: `examples/adapters/openai_compatible_review_adapter.py`

Command adapters are trusted local commands, not sandboxes. Use adapter
allowlists or hash pins in locked-down environments.

Review is contract-aware for git tasks. The latest plan write scope is compared
against the task-scoped changed files, and the review artifact records
`planned_scope`, `actual_scope`, and `scope_mismatches`.

Optional review adapters are supported as an additional semantic review layer:

```bash
bin/axiom --repo-root "$(pwd)" run review "$TASK_ID" \
  --adapter-command "python3 /opt/axiom-adapters/local_reviewer.py"
```

The review adapter cannot bypass deterministic gates. If verification failed,
docs are unresolved, no task diff exists, or changed files escape the planned
write scope, AXIOM returns `changes_requested` or `blocked` before any semantic
adapter can turn the review into a pass.

Verification commands are run through the tool broker with policy checks,
timeouts, stdout/stderr capture limits, and optional strict allowlists. See
[docs/POLICY.md](docs/POLICY.md) for command policy, `.axiom/policy.yaml`,
cleanup safety, and adapter trust boundaries.

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
- native local model server integrations beyond the small OpenAI-compatible
  reference plan/review shims
- reproducible builds
- native macOS signing or notarization

The current adapter support is deliberately narrow: AXIOM can invoke an
explicit local command adapter for `run plan`, `run execute`, and optional
semantic `run review`, passing a structured JSON request on stdin and reading
JSON from stdout. This is enough to integrate a local model shim or a host-agent
wrapper without making AXIOM depend on a single provider.

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
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --force --discard-changes
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --only-if-done --force --delete-branch
```

Default cleanup removes only the managed worktree and keeps the task branch.
`--force` authorizes cleanup, but it does not discard dirty worktree changes.
Dirty worktrees require explicit `--discard-changes`. `--delete-branch` uses
safe `git branch -d`; unmerged branches are not force-deleted.

Runtime diagnostics:

```bash
bin/axiom --repo-root "$(pwd)" doctor
bin/axiom --repo-root "$(pwd)" doctor --json
```

`doctor` checks Python version, schema availability, git/HEAD/worktree
readiness, write permissions, adapter trust environment, policy profiles, and
`.axiom/policy.yaml`.

Non-git repositories and git repositories without an initial commit run in
`isolation_mode: degraded`. In degraded mode, review requires manual smoke
evidence before it can pass.

Schema validation is an AXIOM schema subset, not a full JSON Schema
implementation. It supports the keywords AXIOM uses at runtime: `$schema`,
`title`, `type`, `required`, `properties`, `items`, `enum`, `const`, `$defs`,
and `$ref`. Unsupported keywords such as `additionalProperties` are rejected
instead of being silently ignored.

## Repository Layout

- `src/axiom/`: CLI and core workflow code
- `.axiom/tasks/`: markdown task files
- `.axiom/artifacts/shared/`: persisted phase outputs
- `scripts/`: release metadata generation helpers
- `examples/adapters/`: minimal command adapters for protocol testing
- `src/axiom/schemas/`: packaged runtime schemas
- `.github/workflows/`: test and release workflows
- `tests/unit/`: bootstrap verification suite
