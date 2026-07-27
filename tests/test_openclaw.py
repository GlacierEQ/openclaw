"""Test suite for OpenClaw v2.5 PRO top-tier computer-user engine."""
import unittest
from openclaw import OpenClawEngine

class TestOpenClawEngine(unittest.TestCase):

    def test_top_tier_action_execution(self):
        claw = OpenClawEngine()
        res = claw.execute_action("shortcut", "Cmd+Shift+P", parameters={"keys": ["Meta", "Shift", "P"]})
        self.assertEqual(res["status"], "OPENCLAW_ACTION_EXECUTED")
        self.assertTrue(res["event"]["event_id"].startswith("CLAW-PRO-"))

    def test_vision_sampling(self):
        claw = OpenClawEngine()
        res = claw.sample_vision_state((1920, 1080))
        self.assertEqual(res["status"], "VISION_SAMPLED")
        self.assertEqual(res["viewport_dimensions"], [1920, 1080])

    def test_policy_denial(self):
        claw = OpenClawEngine()
        res = claw.execute_action("unauthorized_kernel_override", "system")
        self.assertEqual(res["status"], "DENIED_BY_AKOS_POLICY")

if __name__ == "__main__":
    unittest.main()
