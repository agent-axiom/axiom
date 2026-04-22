from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.cli import main


class CommandIntegrationTest(unittest.TestCase):
    def test_make_and_show_commands_run_without_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--repo-root", str(repo_root), "make", "Bootstrap task"])
            output = stdout.getvalue().strip()

            self.assertEqual(exit_code, 0)
            self.assertIn(".axiom/tasks", output)

            task_path = Path(output)
            show_stdout = io.StringIO()
            with redirect_stdout(show_stdout):
                show_code = main(["--repo-root", str(repo_root), "show", task_path.name])

        self.assertEqual(show_code, 0)
        self.assertIn("Bootstrap task", show_stdout.getvalue())
