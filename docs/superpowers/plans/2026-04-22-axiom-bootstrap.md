# AXIOM Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first end-to-end AXIOM CLI slice with task files, persisted phase artifacts, lifecycle gating, and tests.

**Architecture:** Use a stdlib-only Python package with a small argparse CLI, dataclass-based domain models, a markdown task file renderer, JSON artifacts for structured phase outputs, and a state machine that blocks illegal transitions. Keep the product deterministic first and expose future adapter seams without relying on model execution yet.

**Tech Stack:** Python 3 standard library, `argparse`, `dataclasses`, `json`, `pathlib`, `subprocess`, `unittest`

---

### Task 1: Repository bootstrap

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `src/axiom/__init__.py`
- Create: `src/axiom/cli.py`
- Test: `tests/unit/test_cli_bootstrap.py`

- [ ] **Step 1: Write the failing bootstrap test**

```python
import unittest

from axiom.cli import build_parser


class BootstrapCLITest(unittest.TestCase):
    def test_parser_exposes_top_level_commands(self) -> None:
        parser = build_parser()
        namespace = parser.parse_args(["list"])
        self.assertEqual(namespace.command, "list")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_cli_bootstrap -v`
Expected: FAIL with `ModuleNotFoundError` or missing `build_parser`

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axiom")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    return parser
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_cli_bootstrap -v`
Expected: PASS

### Task 2: Task model, template, and parser

**Files:**
- Create: `src/axiom/models.py`
- Create: `src/axiom/templates.py`
- Create: `src/axiom/task_file.py`
- Test: `tests/unit/test_task_file.py`

- [ ] **Step 1: Write the failing parser test**

```python
import tempfile
import unittest
from pathlib import Path

from axiom.task_file import load_task


class TaskFileTest(unittest.TestCase):
    def test_load_task_reads_frontmatter_and_sections(self) -> None:
        content = """---
id: AX-20260422-001
title: Example task
status: draft
review_required: true
verification_required: true
manual_smoke_required: true
---

# Example

## Objective
Ship it.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "task.md"
            path.write_text(content, encoding="utf-8")
            task = load_task(path)
        self.assertEqual(task.metadata.id, "AX-20260422-001")
        self.assertEqual(task.sections["Objective"], "Ship it.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_task_file -v`
Expected: FAIL with missing module or missing `load_task`

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class TaskMetadata:
    id: str
    title: str
    status: str
    review_required: bool
    verification_required: bool
    manual_smoke_required: bool


@dataclass
class TaskDocument:
    metadata: TaskMetadata
    title: str
    sections: dict[str, str]
```

```python
REQUIRED_SECTIONS = [
    "Objective",
    "Scope",
    "Invariants",
    "Assumptions",
    "Repo Anchors",
    "Design",
    "Plan",
    "Execution Log",
    "Verification",
    "Review",
    "Docs Impact",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_task_file -v`
Expected: PASS

### Task 3: State machine and gating rules

**Files:**
- Create: `src/axiom/state_machine.py`
- Modify: `src/axiom/models.py`
- Test: `tests/unit/test_state_machine.py`

- [ ] **Step 1: Write the failing state-machine test**

```python
import unittest

from axiom.models import TaskMetadata
from axiom.state_machine import can_transition


class StateMachineTest(unittest.TestCase):
    def test_finish_requires_review_and_verify_pass(self) -> None:
        metadata = TaskMetadata(
            id="AX-1",
            title="Task",
            status="review.passed",
            review_required=True,
            verification_required=True,
            manual_smoke_required=True,
        )
        allowed, reason = can_transition(
            current_status=metadata.status,
            next_status="done",
            verify_passed=False,
            review_passed=True,
            manual_smoke_complete=True,
        )
        self.assertFalse(allowed)
        self.assertIn("verify", reason)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_state_machine -v`
Expected: FAIL with missing `can_transition`

- [ ] **Step 3: Write minimal implementation**

```python
def can_transition(
    *,
    current_status: str,
    next_status: str,
    verify_passed: bool = False,
    review_passed: bool = False,
    manual_smoke_complete: bool = False,
) -> tuple[bool, str]:
    if next_status == "done":
        if not verify_passed:
            return False, "finish requires verify.passed"
        if not review_passed:
            return False, "finish requires review.passed"
        if not manual_smoke_complete:
            return False, "finish requires completed manual smoke checks"
    return True, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_state_machine -v`
Expected: PASS

### Task 4: Artifact persistence and phase summaries

**Files:**
- Create: `src/axiom/artifacts.py`
- Modify: `src/axiom/models.py`
- Test: `tests/unit/test_artifacts.py`

- [ ] **Step 1: Write the failing artifact test**

```python
import json
import tempfile
import unittest
from pathlib import Path

from axiom.artifacts import write_phase_result


class ArtifactStoreTest(unittest.TestCase):
    def test_write_phase_result_persists_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_phase_result(
                repo_root=root,
                task_id="AX-1",
                phase="plan",
                payload={"summary": "ok"},
            )
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"], "ok")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_artifacts -v`
Expected: FAIL with missing `write_phase_result`

- [ ] **Step 3: Write minimal implementation**

```python
def write_phase_result(*, repo_root: Path, task_id: str, phase: str, payload: dict) -> Path:
    phase_root = repo_root / ".axiom" / "artifacts" / "shared" / task_id / phase / "attempt-001"
    phase_root.mkdir(parents=True, exist_ok=True)
    result_path = phase_root / "result.json"
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return result_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_artifacts -v`
Expected: PASS

### Task 5: Repository-aware services and task creation

**Files:**
- Create: `src/axiom/config.py`
- Create: `src/axiom/git.py`
- Modify: `src/axiom/task_file.py`
- Modify: `src/axiom/cli.py`
- Test: `tests/unit/test_make_task.py`

- [ ] **Step 1: Write the failing task-creation test**

```python
import tempfile
import unittest
from pathlib import Path

from axiom.task_file import create_task


class MakeTaskTest(unittest.TestCase):
    def test_create_task_writes_markdown_file_under_axiom_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(repo_root=repo_root, title="Add verify gate", kind="feature")
        self.assertTrue(task_path.exists())
        self.assertIn(".axiom/tasks", str(task_path))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_make_task -v`
Expected: FAIL with missing `create_task`

- [ ] **Step 3: Write minimal implementation**

```python
def create_task(*, repo_root: Path, title: str, kind: str) -> Path:
    now = datetime.now(timezone.utc)
    task_id = f"AX-{now:%Y%m%d}-001"
    slug = slugify(title)
    task_dir = repo_root / ".axiom" / "tasks" / f"{now:%Y}" / f"{now:%m}"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_path = task_dir / f"{task_id}-{slug}.md"
    task_path.write_text(render_new_task(task_id=task_id, title=title, kind=kind, repo_root=repo_root), encoding="utf-8")
    return task_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_make_task -v`
Expected: PASS

### Task 6: Phase commands and lifecycle integration

**Files:**
- Create: `src/axiom/phases.py`
- Modify: `src/axiom/cli.py`
- Modify: `src/axiom/task_file.py`
- Test: `tests/unit/test_lifecycle_flow.py`

- [ ] **Step 1: Write the failing lifecycle test**

```python
import json
import tempfile
import unittest
from pathlib import Path

from axiom.phases import run_plan, run_verify, run_review, finish_task
from axiom.task_file import create_task, load_task


class LifecycleFlowTest(unittest.TestCase):
    def test_finish_blocks_until_verify_and_review_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(repo_root=repo_root, title="Lifecycle", kind="feature")
            run_plan(task_path)
            blocked = finish_task(task_path)
            self.assertFalse(blocked.allowed)
            run_verify(task_path, automated_checks=[{"name": "unit", "command": "python -m unittest", "status": "passed"}], manual_smoke=[{"id": "smoke-1", "status": "passed", "notes": "ok"}])
            run_review(task_path, findings=[])
            allowed = finish_task(task_path)
            self.assertTrue(allowed.allowed)
            self.assertEqual(load_task(task_path).metadata.status, "done")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_lifecycle_flow -v`
Expected: FAIL with missing phase functions

- [ ] **Step 3: Write minimal implementation**

```python
def run_plan(task_path: Path) -> Path:
    payload = {
        "summary": "Bootstrap plan ready",
        "steps": [],
        "manual_smoke": [{"id": "smoke-1", "instruction": "Run the changed command manually"}],
        "stop_conditions": [],
    }
    return write_phase_result(repo_root=repo_root_for(task_path), task_id=load_task(task_path).metadata.id, phase="plan", payload=payload)
```

```python
def finish_task(task_path: Path) -> FinishDecision:
    task = load_task(task_path)
    verify_result = latest_phase_result(repo_root_for(task_path), task.metadata.id, "verify")
    review_result = latest_phase_result(repo_root_for(task_path), task.metadata.id, "review")
    allowed, reason = can_transition(
        current_status=task.metadata.status,
        next_status="done",
        verify_passed=verify_result.get("outcome") == "passed",
        review_passed=review_result.get("outcome") == "pass",
        manual_smoke_complete=all(item["status"] in {"passed", "waived"} for item in verify_result.get("manual_smoke", [])),
    )
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_lifecycle_flow -v`
Expected: PASS

### Task 7: Full verification run

**Files:**
- Modify: `src/axiom/cli.py`
- Modify: `src/axiom/phases.py`
- Test: `tests/unit/test_cli_commands.py`

- [ ] **Step 1: Write the failing CLI integration test**

```python
import tempfile
import unittest
from pathlib import Path

from axiom.cli import main


class CommandIntegrationTest(unittest.TestCase):
    def test_make_and_show_commands_run_without_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            exit_code = main(["--repo-root", str(repo_root), "make", "Bootstrap task"])
        self.assertEqual(exit_code, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_cli_commands -v`
Expected: FAIL because `main` does not support repo-root or `make`

- [ ] **Step 3: Write minimal implementation**

```python
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "make":
        path = create_task(repo_root=Path(args.repo_root), title=args.title, kind=args.kind)
        print(path)
        return 0
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_cli_commands -v`
Expected: PASS

### Task 8: Final repo-level verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-22-axiom-bootstrap-design.md`
- Modify: `docs/superpowers/plans/2026-04-22-axiom-bootstrap.md`

- [ ] **Step 1: Run the full unit suite**

Run: `python -m unittest discover -s tests/unit -v`
Expected: PASS with 0 failures

- [ ] **Step 2: Run the end-to-end smoke flow**

Run: `python -m axiom.cli --repo-root "$(pwd)" make "Demo task"`
Expected: PASS and print task path

- [ ] **Step 3: Record the observed behavior in docs**

```markdown
- Verified `make`, `run plan`, `run verify`, `run review`, and `finish` locally against a temporary repository root.
```

- [ ] **Step 4: Re-run the full unit suite**

Run: `python -m unittest discover -s tests/unit -v`
Expected: PASS with 0 failures
