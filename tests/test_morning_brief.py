"""Tests for morning_brief cron script."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.morning_brief import compile_brief, get_weather


class TestGetWeather(unittest.TestCase):
    @patch("scripts.morning_brief.subprocess.run")
    def test_returns_formatted_weather(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="+22°C, Sunny")
        result = get_weather("Berlin")
        self.assertIn("Berlin", result)
        self.assertIn("+22°C", result)
        self.assertIn("🌤️", result)

    @patch("scripts.morning_brief.subprocess.run")
    def test_returns_empty_on_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = get_weather("Berlin")
        self.assertEqual(result, "")

    def test_empty_city_returns_empty(self):
        result = get_weather("")
        self.assertEqual(result, "")

    @patch("scripts.morning_brief.subprocess.run")
    def test_unknown_location(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Unknown location")
        result = get_weather("Fakecity")
        self.assertEqual(result, "")


class TestCompileBrief(unittest.TestCase):
    @patch("scripts.morning_brief._system_health")
    @patch("scripts.morning_brief._memory_stats")
    @patch("scripts.morning_brief._blocked_and_failed")
    @patch("scripts.morning_brief._queued_tasks")
    @patch("scripts.morning_brief._completed_tasks_24h")
    @patch("scripts.morning_brief.get_weather")
    @patch("scripts.morning_brief._read_config")
    def test_compile_brief_all_sections(self, mock_config, mock_weather,
                                         mock_completed, mock_queued,
                                         mock_blocked, mock_memory, mock_health):
        mock_config.side_effect = lambda k, d="": {"user.timezone": "UTC", "user.city": "Berlin"}.get(k, d)
        mock_weather.return_value = "🌤️ Weather in Berlin: +20°C, Clear"
        mock_completed.return_value = (2, ["Task A", "Task B"])
        mock_queued.return_value = (1, ["Task C"])
        mock_blocked.return_value = (0, 0)
        mock_memory.return_value = {"new_memories": 5, "total_memories": 100, "knowledge_count": 42, "consolidation_runs": 1}
        mock_health.return_value = {"gateway_up": True, "disk_free_mb": 5000, "db_sizes": {"memory.db": 100}, "last_health": "healthy"}

        brief = compile_brief()
        self.assertIn("Morning Brief", brief)
        self.assertIn("Weather", brief)
        self.assertIn("Yesterday", brief)
        self.assertIn("Today", brief)
        self.assertIn("Memory", brief)
        self.assertIn("System", brief)
        self.assertIn("Task A", brief)

    @patch("scripts.morning_brief._system_health")
    @patch("scripts.morning_brief._memory_stats")
    @patch("scripts.morning_brief._blocked_and_failed")
    @patch("scripts.morning_brief._queued_tasks")
    @patch("scripts.morning_brief._completed_tasks_24h")
    @patch("scripts.morning_brief.get_weather")
    @patch("scripts.morning_brief._read_config")
    def test_no_city_skips_weather(self, mock_config, mock_weather,
                                    mock_completed, mock_queued,
                                    mock_blocked, mock_memory, mock_health):
        mock_config.return_value = ""
        mock_weather.return_value = ""
        mock_completed.return_value = (0, [])
        mock_queued.return_value = (0, [])
        mock_blocked.return_value = (0, 0)
        mock_memory.return_value = {"new_memories": 0, "total_memories": 0, "knowledge_count": 0, "consolidation_runs": 0}
        mock_health.return_value = {"gateway_up": True, "disk_free_mb": 5000, "db_sizes": {}, "last_health": "healthy"}

        brief = compile_brief()
        self.assertIn("Morning Brief", brief)
        self.assertNotIn("Weather", brief)

    @patch("scripts.morning_brief._system_health")
    @patch("scripts.morning_brief._memory_stats")
    @patch("scripts.morning_brief._blocked_and_failed")
    @patch("scripts.morning_brief._queued_tasks")
    @patch("scripts.morning_brief._completed_tasks_24h")
    @patch("scripts.morning_brief.get_weather")
    @patch("scripts.morning_brief._read_config")
    def test_timezone_handling(self, mock_config, mock_weather,
                                mock_completed, mock_queued,
                                mock_blocked, mock_memory, mock_health):
        mock_config.side_effect = lambda k, d="": {"user.timezone": "America/New_York", "user.city": ""}.get(k, d)
        mock_weather.return_value = ""
        mock_completed.return_value = (0, [])
        mock_queued.return_value = (0, [])
        mock_blocked.return_value = (0, 0)
        mock_memory.return_value = {"new_memories": 0, "total_memories": 0, "knowledge_count": 0, "consolidation_runs": 0}
        mock_health.return_value = {"gateway_up": True, "disk_free_mb": 5000, "db_sizes": {}, "last_health": "healthy"}

        brief = compile_brief()
        # Should not crash with non-UTC timezone
        self.assertIn("Morning Brief", brief)


if __name__ == "__main__":
    unittest.main()
