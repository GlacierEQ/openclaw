"""Test suite for OpenClaw computer-user engine."""
import unittest
from openclaw import OpenClawEngine

class TestOpenClawEngine(unittest.TestCase):

    def test_action_execution(self):
        claw = OpenClawEngine()
        res = claw.execute_action("click", "button#submit")
        self.assertEqual(res["status"], "OPENCLAW_ACTION_EXECUTED")
        self.assertTrue(res["event"]["event_id"].startswith("CLAW-"))

    def test_policy_denial(self):
        claw = OpenClawEngine()
        res = claw.execute_action("unauthorized_kernel_override", "system")
        self.assertEqual(res["status"], "DENIED_BY_POLICY")

if __name__ == "__main__":
    unittest.main()
