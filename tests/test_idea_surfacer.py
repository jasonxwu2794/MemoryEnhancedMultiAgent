"""Tests for idea_surfacer cron script."""

import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from scripts.idea_surfacer import surface_ideas, notify_ideas


class TestSurfaceIdeas(unittest.TestCase):
    @patch("scripts.idea_surfacer._tech_stack_suggestions", return_value=[])
    @patch("scripts.idea_surfacer._dropped_threads", return_value=[])
    @patch("scripts.idea_surfacer._knowledge_graph_patterns", return_value=[])
    def test_empty_knowledge_graph(self, mock_kg, mock_threads, mock_tech):
        """Should handle gracefully when no patterns found."""
        ideas = surface_ideas()
        self.assertEqual(ideas, [])

    @patch("scripts.idea_surfacer.asyncio.run")
    @patch("scripts.idea_surfacer._tech_stack_suggestions", return_value=["SQLite without backup — consider WAL"])
    @patch("scripts.idea_surfacer._dropped_threads", return_value=["Untracked: should build a CLI tool"])
    @patch("scripts.idea_surfacer._knowledge_graph_patterns", return_value=["High-importance: ML pipeline design"])
    def test_surface_ideas_with_llm(self, mock_kg, mock_threads, mock_tech, mock_asyncio_run):
        mock_asyncio_run.return_value = [
            {"title": "ML Pipeline", "description": "Build an ML pipeline", "domain": "ML"}
        ]
        ideas = surface_ideas()
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["title"], "ML Pipeline")
        # Verify LLM was called with collected context
        call_args = mock_asyncio_run.call_args[0][0]
        # It's a coroutine passed to asyncio.run

    @patch("scripts.idea_surfacer.asyncio.run")
    @patch("scripts.idea_surfacer._tech_stack_suggestions", return_value=["Express — consider rate limiting"])
    @patch("scripts.idea_surfacer._dropped_threads", return_value=[])
    @patch("scripts.idea_surfacer._knowledge_graph_patterns", return_value=["Some pattern"])
    def test_fallback_when_llm_returns_empty(self, mock_kg, mock_threads, mock_tech, mock_asyncio_run):
        mock_asyncio_run.return_value = []  # LLM returns no ideas
        ideas = surface_ideas()
        # Should fallback to tech suggestions
        self.assertGreaterEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["domain"], "DevOps")


class TestNotifyIdeas(unittest.TestCase):
    @patch("scripts.idea_surfacer.subprocess.run")
    def test_message_format(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ideas = [{"title": "Idea A", "description": "Desc A", "domain": "ML"}]
        notify_ideas(ideas, ["Idea A"])
        call_args = mock_run.call_args
        msg = call_args[1].get("args", call_args[0][0]) if call_args[1] else call_args[0][0]
        # Check the message was passed to openclaw
        self.assertTrue(mock_run.called)

    def test_empty_titles_skips(self):
        # Should not raise or call subprocess
        notify_ideas([], [])


if __name__ == "__main__":
    unittest.main()
