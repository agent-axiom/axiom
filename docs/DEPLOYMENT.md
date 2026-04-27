# AXIOM Deployment And Usage

AXIOM has two layers:
- AXIOM runtime: the local `axiom` CLI, installed once in the environment
- Project state: the `.axiom/` directory inside each target repository

The intended operational model is:
- platform or infra team makes `axiom` available inside the closed environment
- user or local agent runs `axiom` against a target project
- AXIOM writes task files and artifacts into that target project

The end user should not need to clone AXIOM into every repository by hand.

## Do Users Need To Clone AXIOM?

For this bootstrap version:
- yes, AXIOM must exist locally somewhere at least once
- no, it does not need to be copied into every target project

Example:

```bash
git clone <internal-axiom-repo> ~/tools/axiom
~/tools/axiom/bin/axiom --repo-root /repos/payments make "fix retry logic"
```

With a central install:

```bash
axiom --repo-root /repos/payments make "fix retry logic"
```

## Closed Infrastructure Model

Recommended setup:

1. Make AXIOM available locally as an internal package, internal mirror, or
   vendored tool directory.
2. Open the target project repository.
3. Run AXIOM against that repository.
4. Let AXIOM create `.axiom/tasks/...` and `.axiom/artifacts/...` inside the
   target repository.

AXIOM behaves like a local toolchain component, not like a cloud service.

## Deployment Modes

### Central Install

Best default for closed infrastructure.

```bash
axiom --repo-root /repos/payments make "fix retry logic"
```

Use this when a platform team can install AXIOM once on developer workstations,
VMs, or jump hosts.

### Internal Mirror Or Sidecar Repo

Good when the environment allows internal git access but not internet access.

```bash
/opt/axiom/bin/axiom --repo-root /repos/payments make "fix retry logic"
```

Mirror AXIOM internally, clone it once into `/opt/axiom` or `/srv/tools/axiom`,
then run the launcher against any project.

### Vendored Into A Project

Good for highly locked-down or audit-heavy environments.

```bash
/repos/payments/tools/axiom/bin/axiom --repo-root /repos/payments make "fix retry logic"
```

This is heavier operationally, but simplest to audit in fully isolated environments.

## Human Operator Flow

```bash
git clone <internal-axiom-repo> ~/tools/axiom
cd ~/tools/axiom
make test

TASK_PATH=$(~/tools/axiom/bin/axiom \
  --repo-root /repos/myproject \
  make "fix invoice rounding")
TASK_ID=$(basename "$TASK_PATH" | sed -E 's/^(AX-[0-9]{8}-[0-9]{3})-.*$/\1/')

~/tools/axiom/bin/axiom --repo-root /repos/myproject list
~/tools/axiom/bin/axiom --repo-root /repos/myproject run design "$TASK_ID"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run plan "$TASK_ID"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run execute "$TASK_ID" \
  --note "Applied implementation changes"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run verify "$TASK_ID" \
  --check "python3 -m unittest discover -s tests/unit -v" \
  --manual-smoke "smoke-1:passed:Observed expected runtime behavior"
~/tools/axiom/bin/axiom --repo-root /repos/myproject run review "$TASK_ID"
~/tools/axiom/bin/axiom --repo-root /repos/myproject finish "$TASK_ID"
```

Result:
- AXIOM stays in `~/tools/axiom`
- workflow state for actual work is written into `/repos/myproject/.axiom/`

## Local Agent Instructions

### AXIOM Already Installed

```text
Work on repository `/repos/myproject` through AXIOM only.
Use `axiom --repo-root /repos/myproject ...` for task creation and phase transitions.
Create a task named `fix invoice rounding`, then drive it through `design`,
`plan`, `execute`, `verify`, `review`, and `finish`.
Keep all persisted state in the project's `.axiom/` directory and do not rely
on chat history as the source of truth.
```

### AXIOM Not Installed Yet

```text
If AXIOM is not already present locally, clone the internal AXIOM repository
into `/opt/axiom`.
After that, work on repository `/repos/myproject` through
`/opt/axiom/bin/axiom --repo-root /repos/myproject ...`.
Create a task named `fix invoice rounding`, then drive it through `design`,
`plan`, `execute`, `verify`, `review`, and `finish`.
Persist workflow state in `/repos/myproject/.axiom/`.
```

### Vendored AXIOM Inside The Project

```text
Use the vendored AXIOM runtime at `/repos/myproject/tools/axiom/bin/axiom`.
Run all workflow actions against repository `/repos/myproject` with
`--repo-root /repos/myproject`.
Create a task named `fix invoice rounding`, then drive it through `design`,
`plan`, `execute`, `verify`, `review`, and `finish`.
Keep the task file authoritative.
```

## Usage Scenarios

### One Developer, One Closed Repository

Clone AXIOM once into a local tools directory and run
`bin/axiom --repo-root /path/to/project ...`.

### Internal Platform Team Supports Many Repositories

Install AXIOM once as an internal binary or package and expose `axiom` in `PATH`.

### Local Coding Agent Works Across Multiple Projects

Keep AXIOM installed centrally or in `/opt/axiom`, and instruct the agent to
always operate through `axiom --repo-root <project>`.

### Fully Air-Gapped Or Audit-Heavy Repository

Vendor AXIOM into the project under `tools/axiom/`. This improves auditability
but makes upgrades heavier.
