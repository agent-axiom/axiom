from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.cli import main
from axiom.version import build_metadata


class VersionCommandTest(unittest.TestCase):
    def test_build_metadata_contains_expected_fields(self) -> None:
        metadata = build_metadata().to_dict()
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertIn("git_commit", metadata)
        self.assertIn("git_tag", metadata)
        self.assertIn("build_timestamp", metadata)
        self.assertIn("source_repo", metadata)

    def test_version_command_prints_verbose_metadata(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["version", "--verbose"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("version: 0.1.0", output)
        self.assertIn("git_commit:", output)
        self.assertIn("source_repo:", output)

    def test_version_command_short_output_is_plain_version(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["version"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "0.1.0")
