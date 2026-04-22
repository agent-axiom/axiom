from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.cli import build_parser


class BootstrapCLITest(unittest.TestCase):
    def test_parser_exposes_top_level_commands(self) -> None:
        parser = build_parser()
        namespace = parser.parse_args(["list"])
        self.assertEqual(namespace.command, "list")

    def test_run_subparser_captures_phase_and_task(self) -> None:
        parser = build_parser()
        namespace = parser.parse_args(["run", "plan", "AX-1"])
        self.assertEqual(namespace.command, "run")
        self.assertEqual(namespace.phase, "plan")
        self.assertEqual(namespace.task, "AX-1")
