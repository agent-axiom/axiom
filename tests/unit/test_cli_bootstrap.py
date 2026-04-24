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

    def test_run_plan_accepts_adapter_command(self) -> None:
        parser = build_parser()
        namespace = parser.parse_args(["run", "plan", "AX-1", "--adapter-command", "python3 adapter.py"])
        self.assertEqual(namespace.adapter_command, "python3 adapter.py")

    def test_policy_approve_keeps_top_level_command(self) -> None:
        parser = build_parser()
        namespace = parser.parse_args(
            ["policy", "approve", "--command", "git push --dry-run", "--reason", "human approved"]
        )
        self.assertEqual(namespace.command, "policy")
        self.assertEqual(namespace.policy_command, "approve")
        self.assertEqual(namespace.policy_target_command, "git push --dry-run")
