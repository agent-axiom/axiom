# AXIOM

AXIOM is a local-first workflow layer for coding agents. This bootstrap slice implements a deterministic CLI around one markdown task file per task, persisted phase artifacts, and hard completion gates for verification and review.

AXIOM is not a prompt pack and not a giant autonomous IDE. The core idea is that the workflow lives in local files and a deterministic CLI, not in chat history.

## Bootstrap scope

This first slice includes:
- one markdown task file per task under `.axiom/tasks/`
- structured JSON artifacts under `.axiom/artifacts/shared/`
- a lifecycle CLI with `make`, `resume`, `list`, `show`, `diff`, `run <phase>`, and `finish`
- mandatory verification and review gates before completion

This slice is intentionally deterministic and stdlib-only. It defines the workflow seams for model adapters without requiring an LLM to run.

## What The Binary Actually Does

The `axiom` binary is a local workflow engine.

It does not just route between prompt files. Its job is to enforce workflow discipline around an agent or model:
- create and update one markdown task file per task
- enforce task status transitions
- persist phase artifacts under `.axiom/artifacts/`
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

## Human-Driven Usage

The simplest workflow is that a human runs the CLI directly inside a project:

```bash
bin/axiom --repo-root "$(pwd)" make "Add verify gate"
bin/axiom --repo-root "$(pwd)" run design AX-20260422-001
bin/axiom --repo-root "$(pwd)" run plan AX-20260422-001
bin/axiom --repo-root "$(pwd)" run execute AX-20260422-001 --note "Applied code changes"
bin/axiom --repo-root "$(pwd)" run verify AX-20260422-001 --check "python3 -m unittest discover -s tests/unit -v" --manual-smoke "smoke-1:passed:Observed expected behavior"
bin/axiom --repo-root "$(pwd)" run review AX-20260422-001
bin/axiom --repo-root "$(pwd)" finish AX-20260422-001
```

That flow is explicit on purpose. AXIOM is meant to make the process inspectable, not magical.

## Agent-Driven Usage

AXIOM also works as a local control plane for a coding agent.

The user tells the agent something like:

> Create an AXIOM task for fixing invoice rounding in `/repos/payments` and work through AXIOM phases.

Then the agent runs local commands such as:

```bash
axiom --repo-root /repos/payments make "fix invoice rounding"
axiom --repo-root /repos/payments run design AX-20260423-001
axiom --repo-root /repos/payments run plan AX-20260423-001
...
```

In this model:
- the agent is the operator
- AXIOM is the workflow engine
- the task file and artifacts are the persisted state

If the agent crashes or the host changes, work is resumed from the task file, not from chat memory.

## Quick start

```bash
bin/axiom --repo-root "$(pwd)" make "Add verify gate"
bin/axiom --repo-root "$(pwd)" list
bin/axiom --repo-root "$(pwd)" run design AX-20260422-001
bin/axiom --repo-root "$(pwd)" run plan AX-20260422-001
bin/axiom --repo-root "$(pwd)" run execute AX-20260422-001 --note "Applied code changes"
bin/axiom --repo-root "$(pwd)" run verify AX-20260422-001 --check "python3 -m unittest discover -s tests/unit -v" --manual-smoke "smoke-1:passed:Observed expected behavior"
bin/axiom --repo-root "$(pwd)" run review AX-20260422-001
bin/axiom --repo-root "$(pwd)" finish AX-20260422-001
```

For local development, `bin/axiom` sets `PYTHONPATH=src` so the CLI works without installing the package first.

## Current Bootstrap Limitation

This repository currently implements the workflow engine and task/artifact model first.

It does not yet ship:
- real model adapters
- real host-agent adapters
- real worktree provisioning

Those are the next layers. The current slice proves the load-bearing part first:
- task file lifecycle
- persisted artifacts
- verification and review gates
- deterministic local CLI control

## Repository layout

- `src/axiom/`: CLI and core workflow code
- `.axiom/tasks/`: markdown task files
- `.axiom/artifacts/shared/`: persisted phase outputs
- `tests/unit/`: bootstrap verification suite
