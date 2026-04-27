# AXIOM Policy And Trust Boundaries

AXIOM policy is a guardrail, not a sandbox.

It blocks known-dangerous direct commands and shell control operators, but it
cannot prevent a trusted interpreter command from doing arbitrary work. Treat
AXIOM policy as workflow enforcement and audit evidence, not OS isolation.

## Command Policy Profiles

Verification commands run through the tool broker with policy checks, timeouts,
and stdout/stderr capture limits.

Profiles:
- `standard`: default guardrails with escalation for dependency changes and sensitive git operations
- `strict`: only known test runners, commands passed through `--policy-allow`,
  or commands listed in `.axiom/policy.yaml`
- `permissive`: allows escalation-class commands but still denies destructive
  and shell-control patterns

Strict example:

```bash
bin/axiom --repo-root "$(pwd)" run verify "$TASK_ID" \
  --policy-profile strict \
  --check "python3 -m unittest discover -s tests/unit -v" \
  --manual-smoke "smoke-1:passed:Observed expected behavior"
```

## Repo-Local Policy Config

Repo-local strict allowlists use AXIOM's intentionally small policy YAML subset:

```yaml
verify:
  strict_allow:
    - python3 -m unittest discover -s tests/unit -v
```

Malformed policy files block strict verification instead of being ignored.

`.axiom/policy.yaml` is privileged trust configuration. It should be owned by a
human or platform operator, not opportunistically modified by the task agent. If
a task changes `.axiom/policy.yaml` or `.axiom/policy.yml`, deterministic review
requests changes before finish even when the file is inside the declared plan
scope.

## Policy Approvals

Escalated commands are blocked until explicitly approved:

```bash
bin/axiom --repo-root "$(pwd)" policy approve \
  --task "$TASK_ID" \
  --command "git push --dry-run" \
  --reason "human reviewed this dry-run push"

bin/axiom --repo-root "$(pwd)" policy approvals
```

Approvals are local artifacts scoped to the repository, command, task id, and worktree.

## Adapter Trust

Command adapters are trusted local commands. AXIOM does not sandbox them. They
run in the task worktree and can read or write files available to the current OS
user.

Use adapters only from trusted internal paths. Optional guardrails:
- `AXIOM_ADAPTER_ALLOWLIST`: path-separated list of allowed adapter script or executable paths
- `AXIOM_ADAPTER_SHA256`: path-separated `absolute_path=sha256` pins for adapter files

Adapter protocol details live in [ADAPTER_PROTOCOL.md](ADAPTER_PROTOCOL.md).

## Cleanup Safety

Worktree cleanup is intentionally conservative:

```bash
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --dry-run
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --force
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --force --discard-changes
bin/axiom --repo-root "$(pwd)" cleanup "$TASK_ID" --only-if-done --force --delete-branch
```

Default cleanup removes only the managed worktree and keeps the task branch.
`--force` authorizes cleanup, but it does not discard dirty worktree changes.
Dirty worktrees require explicit `--discard-changes`. `--delete-branch` uses
safe `git branch -d`; unmerged branches are not force-deleted.
