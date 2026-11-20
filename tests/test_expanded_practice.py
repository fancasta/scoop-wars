import json
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection

from expanded_practice import FIXTURE_KEY, FixtureProxy, fixture_payload, load_fixture, score, timing


def case(case_id="sample"):
    article = {
        "url": "https://paper.example/story", "title": "Town buys 52 panels", "published_age_minutes": 15,
        "full_content": "The town approved 52 panels at 8 a.m. today.",
    }
    return {
        "id": case_id, "split": "development", "category": "sample", "clue": "A town approved 52 panels.",
        "expected": {"urls": [article["url"]], "summary_facts": [["approv"], ["52"]]},
        "searches": [{
            "match": {"language": ["en"], "query_any": ["panel"], "full_content": True},
            "response": {"data": {"results": [article], "subjects": []}},
        }],
    }


class FixtureTests(unittest.TestCase):
    def test_fixtures_cannot_include_real_publisher_urls(self):
        value = case()
        value["searches"][0]["response"]["data"]["results"][0]["url"] = "https://example.com/real"
        with self.assertRaisesRegex(ValueError, "reserved synthetic article domain"):
            load_fixture(json.dumps({"version": 1, "cases": [value]}).encode())

    def test_publish_times_are_relative_and_full_text_is_requested(self):
        response = case()["searches"][0]["response"]
        response["data"]["subjects"] = [{"top_news": {"published_age_minutes": -1}, "sub_news": [{"published_age_minutes": None}]}]
        now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        actual = fixture_payload(response, False, now)["data"]
        self.assertEqual(actual["results"][0]["time_published"], "2026-11-18T11:45:00+00:00")
        self.assertNotIn("full_content", actual["results"][0])
        self.assertEqual(actual["subjects"][0]["top_news"]["time_published"], "2026-11-18T12:01:00+00:00")
        self.assertIsNone(actual["subjects"][0]["sub_news"][0]["time_published"])
        self.assertIn("published_age_minutes", response["data"]["results"][0])

    def test_http_fixture_requires_synthetic_auth_and_tracks_scope_and_budget(self):
        request = {"query": "PANEL", "language": ["en"], "full_content": {"enable": True}}
        with FixtureProxy([case("a"), case("b")]) as proxy:
            server = threading.Thread(target=proxy.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            server.start()

            def post(token, body=request, key=FIXTURE_KEY):
                connection = HTTPConnection("127.0.0.1", proxy.server_port, timeout=2)
                try:
                    connection.request("POST", "/octen/news-search", json.dumps(body), {
                        "x-scoop-token": token, "x-api-key": key,
                    })
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    connection.close()

            try:
                self.assertEqual(post(proxy.tokens["a"], key="bad-key")[0], 403)
                self.assertEqual(post("wrong-case-token")[0], 403)
                status, matched = post(proxy.tokens["a"])
                self.assertEqual(status, 200)
                self.assertTrue(matched["data"]["results"][0]["full_content"])
                self.assertEqual(post(proxy.tokens["a"])[1]["data"]["results"], [])
                self.assertEqual(post(proxy.tokens["a"])[0], 429)
                self.assertEqual(post(proxy.tokens["b"], dict(request, language=["id"]))[1]["data"]["results"], [])
            finally:
                proxy.shutdown()
                server.join()

        self.assertEqual([call["status"] for call in proxy.calls["a"]], [200, 200, 429])
        self.assertFalse(proxy.calls["a"][1]["fixture_step_available"])
        self.assertTrue(proxy.calls["b"][0]["fixture_step_available"])
        self.assertFalse(proxy.calls["b"][0]["matched_fixture"])


class ScoreTests(unittest.TestCase):
    def test_abbreviations_and_stems_work_but_wrong_numbers_do_not(self):
        candidate = {"url": "https://paper.example/story", "summary": "At 8 a.m. the town approved 52 panels.", "searches": ["panels"]}
        attempts = [{"success": True}]
        self.assertEqual(score(case(), candidate, attempts, ["octen.news_search"]), [])
        multi = dict(candidate, summary="The town approved 152 panels. It will install them.")
        self.assertEqual(score(case(), multi, attempts, ["octen.news_search"]), ["invalid_summary_sentence", "missing_summary_facts:2"])

    def test_transport_blank_requires_retry_and_rejects_unauthorized_tools(self):
        fixture = case()
        fixture["expected"] = {"urls": [], "allow_no_success": True}
        blank = {"url": "", "summary": "", "searches": []}
        self.assertEqual(score(fixture, blank, [{"success": False}], []), ["did_not_retry_failed_search"])
        self.assertEqual(score(fixture, blank, [{"success": False}] * 2, ["web_search"]), ["unexpected_tool"])
        self.assertEqual(score(fixture, blank, [{"success": False}] * 2, ["octen.news_search"] * 2), [])

    def test_p90_is_nearest_rank(self):
        self.assertEqual(timing(list(range(1, 11))), {"n": 10, "p50": 5.5, "p90": 9, "max": 10})
