"""Tests for Guardian expanded capabilities: breaking changes, conventions, rollback, review."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.guardian.guardian import GuardianAgent
from agents.common.protocol import AgentRole, AgentMessage, TaskStatus


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_guardian():
    """Create a GuardianAgent with mocked bus and LLM."""
    with patch("agents.common.base_agent.BaseAgent.__init__", return_value=None):
        g = GuardianAgent.__new__(GuardianAgent)
        g.name = "guardian"
        g.role = AgentRole.GUARDIAN
        g.llm = MagicMock()
        g._usage_tracker = MagicMock()
        g._daily_token_budget = 1_000_000
        g._token_counts = {}
        g._hourly_counts = {}
        g._cost_reset_date = "2026-02-13"
        g._hour_reset = 10
        g._security_log = []
        g._max_log_entries = 1000
        g._messages_scanned = 0
        g._issues_found = 0
        g._blocks_issued = 0
        g._system_prompt_text = "You are Guardian."
        return g


class TestDetectBreakingChanges(unittest.TestCase):
    def test_calls_llm_with_diff(self):
        g = _make_guardian()
        g.llm.generate_json = AsyncMock(return_value={
            "content": {
                "breaking_changes": [
                    {
                        "type": "signature_change",
                        "location": "foo.py:10",
                        "description": "Added required param",
                        "callers_updated": False,
                        "affected_callers": ["bar.py"],
                        "severity": "high",
                    }
                ],
                "summary": "1 breaking change",
            }
        })

        issues = _run(g.detect_breaking_changes("diff content here", "caller context"))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["category"], "breaking_change")
        self.assertIn("signature_change", issues[0]["description"])
        # Verify LLM was called with the diff
        call_args = g.llm.generate_json.call_args
        self.assertIn("diff content here", call_args.kwargs.get("prompt", ""))

    def test_empty_diff_returns_empty(self):
        g = _make_guardian()
        issues = _run(g.detect_breaking_changes(""))
        self.assertEqual(issues, [])


class TestEnforceCodeConventions(unittest.TestCase):
    def test_with_rules(self):
        g = _make_guardian()
        g.llm.generate_json = AsyncMock(return_value={
            "content": {
                "violations": [
                    {"rule": "no-print", "location": "app.py:5", "description": "print() used", "severity": "low"}
                ],
                "summary": "1 violation",
            }
        })
        with patch.object(g, "_load_convention_rules", return_value="no-print: Don't use print()"):
            issues = _run(g.enforce_code_conventions("some diff"))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["category"], "convention_violation")

    def test_without_rules_skips(self):
        g = _make_guardian()
        with patch.object(g, "_load_convention_rules", return_value=None):
            issues = _run(g.enforce_code_conventions("some diff"))
        self.assertEqual(issues, [])


class TestMakeRollbackDecision(unittest.TestCase):
    def test_rollback_decision(self):
        g = _make_guardian()
        g.llm.generate_json = AsyncMock(return_value={
            "content": {
                "decision": "rollback",
                "reasoning": "Tests consistently fail",
                "confidence": 0.9,
                "details": "Revert commit abc123",
            }
        })
        result = _run(g.make_rollback_decision("task ctx", 3, "failed 3 times"))
        self.assertEqual(result["decision"], "rollback")
        self.assertEqual(result["failure_count"], 3)

    def test_escalate_on_llm_failure(self):
        g = _make_guardian()
        g.llm.generate_json = AsyncMock(side_effect=Exception("LLM down"))
        result = _run(g.make_rollback_decision("task", 2))
        self.assertEqual(result["decision"], "escalate")

    def test_flag_human(self):
        g = _make_guardian()
        g.llm.generate_json = AsyncMock(return_value={
            "content": {
                "decision": "flag_human",
                "reasoning": "Intentional breaking change",
                "confidence": 0.7,
                "details": "Needs human approval",
            }
        })
        result = _run(g.make_rollback_decision("ctx", 2))
        self.assertEqual(result["decision"], "flag_human")


class TestReviewAggregation(unittest.TestCase):
    def test_review_calls_all_capabilities(self):
        g = _make_guardian()
        g.bus = MagicMock()

        msg = MagicMock(spec=AgentMessage)
        msg.payload = {}
        msg.context = {}
        msg.result = None
        msg.from_agent = AgentRole.BRAIN
        msg.metadata = {}

        g.llm.generate_json = AsyncMock(return_value={
            "content": {"breaking_changes": [], "summary": "None", "violations": [], "decision": "escalate", "reasoning": "", "confidence": 0.5, "details": ""}
        })
        g.llm.generate = AsyncMock(return_value={"content": '{"is_injection": false, "severity": "none", "explanation": ""}'})

        with patch.object(g, "_load_convention_rules", return_value="some rules"):
            result = _run(g.review(
                msg,
                diff="some diff",
                caller_context="callers",
                verification_failure_count=2,
                task_context="task",
                failure_history="history",
            ))

        self.assertIn("verdict", result)
        self.assertIn("issues", result)
        self.assertIn("rollback_decision", result)
        self.assertIsNotNone(result["rollback_decision"])
        self.assertIn("cost_report", result)


if __name__ == "__main__":
    unittest.main()
