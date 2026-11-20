import contextlib
import io
import sys
import unittest
from unittest.mock import patch

import play


class CodexRunTests(unittest.TestCase):
    def run_stub(self, script: str, timeout: float = 5, verbose: bool = False) -> play.Card:
        def command(_workdir, output, run_log):
            return [sys.executable, "-c", script, output, run_log]

        with patch.object(play, "codex_command", side_effect=command):
            return play.run_agent("A practice clue", timeout, verbose)

    def test_launch_event_and_search_time_survive_an_intentional_blank(self):
        script = """
import json, pathlib, sys, time
print('a non-JSON diagnostic', flush=True)
print(json.dumps({'type': 'thread.started'}), flush=True)
sys.stdin.read()
time.sleep(0.1)
event = {'type': 'item.started', 'item': {'type': 'mcp_tool_call', 'server': 'octen', 'tool': 'news_search'}}
print(json.dumps(event), flush=True)
pathlib.Path(sys.argv[2]).write_text(json.dumps({'t': time.time(), 'secs': 0.04, 'status': 200, 'code': 0, 'query': 'search term'}), encoding='utf-8')
pathlib.Path(sys.argv[1]).write_text(json.dumps({'url': '', 'summary': ''}), encoding='utf-8')
"""
        with contextlib.redirect_stderr(io.StringIO()) as shown:
            card = self.run_stub(script, verbose=True)

        self.assertEqual(card.url, "")
        self.assertEqual(card.summary, "")
        self.assertEqual(card.error, "")
        self.assertEqual(card.searches, ["search term"])
        self.assertIn("tool octen.news_search", shown.getvalue())
        self.assertIsNotNone(card.codex_startup_secs)
        self.assertLess(card.codex_startup_secs, card.seconds)
        self.assertTrue(card.search_times[0]["ok"])
        self.assertGreater(card.search_times[0]["started"], card.codex_startup_secs)
        self.assertEqual(card.search_times[0]["duration"], 0.04)

    def test_missing_thread_event_does_not_turn_a_valid_card_into_an_error(self):
        script = """
import json, pathlib, sys
sys.stdin.read()
pathlib.Path(sys.argv[1]).write_text(json.dumps({'url': 'https://example.com', 'summary': 'A report.'}), encoding='utf-8')
"""
        card = self.run_stub(script)

        self.assertIsNone(card.codex_startup_secs)
        self.assertEqual(card.url, "https://example.com")
        self.assertEqual(card.error, "")

    def test_timeout_keeps_startup_sample_and_returns_without_a_card(self):
        script = """
import json, pathlib, sys, time
print(json.dumps({'type': 'thread.started'}), flush=True)
pathlib.Path(sys.argv[2]).write_bytes(b'{"partial":"\\xe6')
time.sleep(10)
"""
        card = self.run_stub(script, timeout=1)

        self.assertIsNotNone(card.codex_startup_secs)
        self.assertEqual(card.url, "")
        self.assertEqual(card.searches, [])
        self.assertIn("timed out", card.error)
        self.assertLess(card.seconds, 10)

    def test_child_retaining_event_pipe_does_not_block_a_completed_card(self):
        script = """
import json, pathlib, subprocess, sys
print(json.dumps({'type': 'thread.started'}), flush=True)
sys.stdin.read()
subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'], stderr=subprocess.DEVNULL)
pathlib.Path(sys.argv[1]).write_text(json.dumps({'url': 'https://example.com', 'summary': 'A report.'}), encoding='utf-8')
"""
        card = self.run_stub(script)

        self.assertIsNotNone(card.codex_startup_secs)
        self.assertEqual(card.url, "https://example.com")
        self.assertEqual(card.error, "")
        self.assertLess(card.seconds, 2)
