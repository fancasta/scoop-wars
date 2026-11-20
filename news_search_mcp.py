"""Octen News Search as an MCP tool for Codex.

play.py starts Codex with this file registered as the `octen` MCP server, so the
agent gets one tool: news_search. Calls go through octen_client.news_search(),
which routes them via the game server so they count for scoring.

Change anything here: parameters, how results are trimmed, extra tools
(other Octen search APIs via octen_client.search(), sharing the 2-call budget; Extract
and Embedding are fine; other search tools and web browsing are not).
API reference: https://docs.octen.ai/capabilities/news-search
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Codex starts this from a temp dir

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer

from octen_client import news_search as octen_news_search  # noqa: E402

mcp = MCPServer("octen")
# The MCP library turns on INFO logging, which makes httpx print every request
# ("HTTP Request: POST ...") into play.py's output. Keep it quiet.
import logging  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)

FULL_ARTICLE_LIMIT = 4
FULL_CONTENT_MAX_TOKENS = 1000
FULL_CONTENT_MAX_CHARS = 4000


def _in_day_window(article: dict, now: datetime) -> bool:
    published = article.get("time_published")
    if not isinstance(published, str) or not published:
        return True
    try:
        date = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return True
    # Leave undated or timezone-ambiguous reports for the agent to verify.
    return date.tzinfo is None or now - timedelta(days=1) <= date <= now


def _article(a: dict, with_full_content: bool) -> dict:
    article = {
        "title": a.get("title"),
        "url": a.get("url"),
        "source": a.get("authors"),
        "published": a.get("time_published"),
        "highlight": (a.get("highlight") or "")[:400],
    }
    if a.get("language"):
        article["language"] = a["language"]
    content = a.get("full_content")
    if with_full_content and isinstance(content, str) and content:
        article["full_content"] = content[:FULL_CONTENT_MAX_CHARS]
    return article


@mcp.tool()
def news_search(
    query: str,
    language: list[str] | None = None,
    time_range: str = "day",
    count: int = 10,
    full_content: bool = False,
) -> str:
    """Search recent news articles with Octen News Search.

    Args:
        query: what to search for.
        language: optional ISO 639-1 codes to restrict results, e.g. ["en"].
        time_range: "day", "week", "month" or "year". Defaults to the last day.
        count: number of articles, 1 to 20.
        full_content: return bounded article text for up to four results so you can check exact details.
    """
    body = {
        "query": query,
        "count": max(1, min(int(count), 20)),
        "time_range": time_range,
        "time_basis": "published",
        "highlight": {"enable": True, "max_tokens": 200},
        "subjects": {"enable": True, "count": 2, "max_sub_news": 5},
    }
    if language:
        body["language"] = language
    if full_content:
        body["full_content"] = {"enable": True, "max_tokens": FULL_CONTENT_MAX_TOKENS}
    data = octen_news_search(body)
    if data.get("code", 0) != 0:
        return json.dumps({"error": data.get("msg") or data.get("error") or "News Search failed", "code": data.get("code")})
    d = data.get("data") or {}
    full_urls: set[str] = set()
    now = datetime.now(timezone.utc)

    def in_window(a: dict) -> bool:
        return time_range != "day" or _in_day_window(a, now)

    def article(a: dict) -> dict:
        url = a.get("url")
        content = a.get("full_content")
        include_full = (
            full_content and bool(url) and url not in full_urls
            and len(full_urls) < FULL_ARTICLE_LIMIT and isinstance(content, str) and bool(content)
        )
        if include_full:
            full_urls.add(url)
        return _article(a, include_full)

    results = [article(a) for a in d.get("results") or [] if in_window(a)]
    stories = []
    for subject in d.get("subjects") or []:
        candidates = [subject.get("top_news") or {}] + list(subject.get("sub_news") or [])
        articles = [article(a) for a in candidates if a.get("url") and in_window(a)]
        if articles:
            stories.append({
                "name": subject.get("name"),
                "summary": subject.get("summary"),
                "started": subject.get("time_start"),
                "articles": articles,
            })
    out = {"results": results, "stories": stories}
    return json.dumps(out, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
