import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import news_search_mcp


class NewsSearchTests(unittest.TestCase):
    def test_default_requests_fresh_highlights_with_the_requested_language(self):
        article = {"url": "https://example.com/news", "title": "今日新闻", "highlight": "Short excerpt", "full_content": "Article body"}
        response = {"data": {"results": [article]}}
        with patch.object(news_search_mcp, "octen_news_search", return_value=response) as proxy:
            result = json.loads(news_search_mcp.news_search("今日新闻", ["zh"], count=99))

        request = proxy.call_args.args[0]
        self.assertEqual(request["language"], ["zh"])
        self.assertEqual(request["time_range"], "day")
        self.assertEqual(request["time_basis"], "published")
        self.assertEqual(request["count"], 20)
        self.assertNotIn("full_content", request)
        self.assertEqual(result["results"][0]["highlight"], "Short excerpt")
        self.assertNotIn("full_content", result["results"][0])

    def test_full_content_is_limited_to_distinct_articles_across_response(self):
        articles = [
            {
                "url": f"https://example.com/{i}",
                "title": f"Article {i}",
                "language": "id",
                "highlight": "Highlight",
                "full_content": "a" * (news_search_mcp.FULL_CONTENT_MAX_CHARS + 1),
            }
            for i in range(6)
        ]
        response = {"data": {
            "results": [articles[0], articles[1], articles[0], dict(articles[2], full_content=None)],
            "subjects": [{"top_news": articles[1], "sub_news": articles[2:]}],
        }}
        with patch.object(news_search_mcp, "octen_news_search", return_value=response) as proxy:
            result = json.loads(news_search_mcp.news_search("berita hari ini", ["id"], full_content=True))

        self.assertEqual(proxy.call_count, 1)
        self.assertEqual(proxy.call_args.args[0]["full_content"], {"enable": True, "max_tokens": 1000})
        views = result["results"] + result["stories"][0]["articles"]
        full = [article for article in views if "full_content" in article]
        self.assertEqual([article["url"] for article in full], [article["url"] for article in articles[:4]])
        self.assertTrue(all(len(article["full_content"]) == news_search_mcp.FULL_CONTENT_MAX_CHARS for article in full))
        self.assertTrue(all(article["language"] == "id" for article in views))

    def test_proxy_budget_errors_are_preserved(self):
        with patch.object(news_search_mcp, "octen_news_search", return_value={"code": 429, "msg": "Budget used"}):
            result = json.loads(news_search_mcp.news_search("news", full_content=True))

        self.assertEqual(result, {"code": 429, "error": "Budget used"})

    def test_day_search_filters_stale_and_future_coverage_in_results_and_groups(self):
        def article(name, published):
            return {"url": f"https://paper.example/{name}", "time_published": published}

        now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        stale = article("stale", "2026-11-17T11:59:59Z")
        future = article("future", "2026-11-18T20:00:01+08:00")
        border = article("boundary", "2026-11-17T20:00:00+08:00")
        undated = article("undated", None)
        malformed = article("unknown", "invalid")
        response = {"data": {
            "results": [stale, future, border, undated, malformed],
            "subjects": [
                {"name": "Expired", "top_news": stale, "sub_news": [future]},
                {"name": "Mixed", "top_news": stale, "sub_news": [border, undated]},
            ],
        }}
        with (
            patch.object(news_search_mcp, "octen_news_search", return_value=response),
            patch.object(news_search_mcp, "datetime", wraps=datetime) as clock,
        ):
            clock.now.return_value = now
            daily = json.loads(news_search_mcp.news_search("meeting"))
            weekly = json.loads(news_search_mcp.news_search("meeting", time_range="week"))

        self.assertEqual([a["url"] for a in daily["results"]], [a["url"] for a in (border, undated, malformed)])
        self.assertEqual([group["name"] for group in daily["stories"]], ["Mixed"])
        self.assertEqual([a["url"] for a in daily["stories"][0]["articles"]], [a["url"] for a in (border, undated)])
        self.assertEqual(len(weekly["results"]), len(response["data"]["results"]))
