from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.task_file import create_task, load_task


class TaskFileTest(unittest.TestCase):
    def test_create_task_writes_markdown_file_under_axiom_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            task_path = create_task(
                repo_root=repo_root,
                title="Add verify gate",
                kind="feature",
                now=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
            )
            task = load_task(task_path)
            self.assertTrue(task_path.exists())
            self.assertIn(".axiom/tasks/2026/04", str(task_path))
            self.assertEqual(task.metadata.id, "AX-20260422-001")
            self.assertEqual(task.metadata.kind, "feature")
            self.assertEqual(task.sections["Objective"], "")
            self.assertIn("Docs Impact", task.sections)

    def test_load_task_reads_frontmatter_and_sections(self) -> None:
        content = """---
id: AX-20260422-001
title: Example task
kind: feature
status: draft
created_at: 2026-04-22T12:00:00+00:00
updated_at: 2026-04-22T12:00:00+00:00
repo_root: /tmp/repo
base_branch: main
branch: axiom/AX-20260422-001-example-task
worktree: /tmp/repo
risk: medium
review_required: true
verification_required: true
manual_smoke_required: true
docs_status: pending
---

# Example task

## Objective
Ship it.

## Scope
Small.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "task.md"
            path.write_text(content, encoding="utf-8")
            task = load_task(path)

        self.assertEqual(task.metadata.id, "AX-20260422-001")
        self.assertEqual(task.metadata.title, "Example task")
        self.assertEqual(task.sections["Objective"], "Ship it.")
        self.assertEqual(task.sections["Scope"], "Small.")
