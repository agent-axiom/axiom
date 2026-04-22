from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from axiom.state_machine import can_transition


class StateMachineTest(unittest.TestCase):
    def test_finish_requires_review_and_verify_pass(self) -> None:
        allowed, reason = can_transition(
            current_status="review.passed",
            next_status="done",
            verify_passed=False,
            review_passed=True,
            manual_smoke_complete=True,
            docs_resolved=True,
        )
        self.assertFalse(allowed)
        self.assertIn("verify", reason)

    def test_finish_requires_docs_disposition(self) -> None:
        allowed, reason = can_transition(
            current_status="review.passed",
            next_status="done",
            verify_passed=True,
            review_passed=True,
            manual_smoke_complete=True,
            docs_resolved=False,
        )
        self.assertFalse(allowed)
        self.assertIn("docs", reason)
