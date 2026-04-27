# Demo Walkthrough

This walkthrough proves the core AXIOM loop in a tiny local repository:

- create one task file
- provision a task worktree
- use a plan adapter
- use an execute adapter
- run real verification plus manual smoke evidence
- run review
- finish only after gates pass

It uses only files in this repository and Python's standard library.

## 1. Create A Demo Repository

```bash
DEMO_REPO=$(mktemp -d)
git -C "$DEMO_REPO" init -b main
git -C "$DEMO_REPO" config user.email axiom@example.test
git -C "$DEMO_REPO" config user.name "AXIOM Demo"
printf "print('base')\n" > "$DEMO_REPO/app.py"
git -C "$DEMO_REPO" add app.py
git -C "$DEMO_REPO" commit -m initial
```

## 2. Create The Task

Run these commands from the AXIOM source checkout:

```bash
TASK_PATH=$(bin/axiom --repo-root "$DEMO_REPO" make "demo adapter loop")
TASK_ID=$(basename "$TASK_PATH" | sed -E 's/^(AX-[0-9]{8}-[0-9]{3})-.*$/\1/')

bin/axiom --repo-root "$DEMO_REPO" run design "$TASK_ID"
```

Add concrete task anchors and docs disposition:

```bash
python3 - "$TASK_PATH" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
text = text.replace(
    "## Repo Anchors\n- Add relevant files or symbols here as the task narrows.",
    "## Repo Anchors\n\n- app.py",
)
text = text.replace(
    "## Docs Impact\nPending documentation decision.",
    "## Docs Impact\n\nNo documentation changes required.",
)
text = text.replace("docs_status: pending", "docs_status: not_needed")
path.write_text(text)
PY
```

## 3. Plan And Execute Through Adapters

```bash
bin/axiom --repo-root "$DEMO_REPO" run plan "$TASK_ID" \
  --adapter-command "python3 $(pwd)/examples/adapters/static_plan_adapter.py"

bin/axiom --repo-root "$DEMO_REPO" run execute "$TASK_ID" \
  --adapter-command "python3 $(pwd)/examples/adapters/file_write_execute_adapter.py"
```

Inspect the task-scoped diff:

```bash
bin/axiom --repo-root "$DEMO_REPO" diff "$TASK_ID"
```

## 4. Verify And Review

```bash
bin/axiom --repo-root "$DEMO_REPO" run verify "$TASK_ID" \
  --check "python3 -c \"print('ok')\"" \
  --manual-smoke "smoke-1:passed:Ran changed path and observed expected output"

bin/axiom --repo-root "$DEMO_REPO" run review "$TASK_ID"
```

Review records the planned scope, actual changed files, and scope mismatches.

## 5. Finish

```bash
bin/axiom --repo-root "$DEMO_REPO" finish "$TASK_ID"
bin/axiom --repo-root "$DEMO_REPO" resume "$TASK_ID"
```

Expected final status:

```text
status: done
next: none
```

Artifacts are persisted under:

```text
$DEMO_REPO/.axiom/artifacts/shared/$TASK_ID/
```

The task file remains the operational source of truth under:

```text
$DEMO_REPO/.axiom/tasks/
```
