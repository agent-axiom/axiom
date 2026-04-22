from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.artifacts import latest_phase_result, write_phase_result


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
            result = latest_phase_result(root, "AX-1", "plan")
            self.assertTrue(path.exists())
            self.assertEqual(result["summary"], "ok")

    def test_multiple_writes_increment_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = write_phase_result(
                repo_root=root,
                task_id="AX-1",
                phase="plan",
                payload={"summary": "first"},
            )
            second = write_phase_result(
                repo_root=root,
                task_id="AX-1",
                phase="plan",
                payload={"summary": "second"},
            )

        self.assertNotEqual(first.parent.name, second.parent.name)
        self.assertEqual(second.parent.name, "attempt-002")
