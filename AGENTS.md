# Scoop Wars starter kit: notes for coding agents

This repo is an agent that finds fresh news stories from vague clues. You are helping a team improve it during an hour-long build. The agent runs inside `codex exec`; this file is not part of its prompt (play.py runs it in an empty temp directory).

See [CONTEXT.md](CONTEXT.md) for current agent behavior and eval evidence, [README.md](README.md) for the fork overview and setup, and [the AI working agreement](docs/AI_WORKING_AGREEMENT.md) for changing and validating the agent.

## Setting up a laptop

If asked to set someone up, work through [Tonight's checklist](docs/event-guide.md#tonights-checklist). Run the terminal steps yourself (install uv and Codex, clone, `cp .env.example .env`, `uv run play.py doctor`). Ask the person for what only they can do: joining the Wi-Fi, claiming credits on the event page, `codex login`, their `OCTEN_API_KEY`, and the `SCOOP_SERVER` and `SCOOP_TOKEN` lines from the event page (step 7). Teams are made by the organizers; don't run `play.py join`. Never print, paste or commit the contents of `.env`.

## Layout

- `play.py`: CLI. `run_agent(clue, timeout) -> Card` builds the `codex exec` command (`codex_command()`), passes `prompt.md` plus the clue on stdin, and reads the final card from `--output-last-message`. `ask`, `eval` and `play` all go through `run_agent()`. It may be replaced by any agent (any model, no Codex) that returns a `Card` in time.
- `prompt.md`: the agent's instructions.
- `octen_client.py`: `news_search(body) -> dict` and `search(api, body) -> dict` (the other allowed Octen search APIs, listed in `SEARCH_APIS`, e.g. `"search"` for Web Search), the only allowed ways to search. They route calls through `$SCOOP_SERVER/octen/<api>` with the team token, which forwards to `https://api.octen.ai/<api>` with the team's `OCTEN_API_KEY` and logs the call. `capture()` collects the queries made in a block, for `Card.searches` (non-News Search calls are prefixed with the API name).
- `news_search_mcp.py`: MCP server (stdio) exposing the `news_search` tool to Codex, built on `octen_client`.
- `judge.py`: the game's judge for links not in the answer key. `eval` uses it. Don't change it; it won't change how the game server judges.
- `card.schema.json`: the final answer shape, `{"url": str, "summary": str}`, enforced with `--output-schema`.

## Hard constraints

- 45 seconds per clue, including Codex startup. `play.py` kills the run at 41 seconds.
- Every search must go through `octen_client` (the game server proxy logs it). Don't wire in Octen's own MCP server, CLI or SDK: they skip the game server, so their calls don't count. Budget: 2 search calls per clue, all Octen search APIs combined; the third returns `{"code": 429}`. Calls are made in parallel at your own risk: both count. A card scores 0 if the team made no News Search call (through the game server) during the clue. Do not use Broad Search, Answer, Search Agent, Deep Research or Auto Search (they run many searches per call), and do not add other web search tools, browsing, or scraping. Octen Extract and Embedding are allowed and don't use the budget.
- Some clues are local: stories covered so far only in Chinese or Indonesian outlets. For those, only an article in that language counts (English coverage is scored wrong). News Search accepts `language: ["zh"]` or `["id"]` and queries in that language.
- The card summary must be one English sentence, whatever language the article is in.
- Keep `card.schema.json` and the `/api/cards` submission format unchanged.

## News Search API

`POST /news-search` with `query` (required, max 500 chars), `count` (1 to 100), `time_range` (`day|week|month|year`) or `start_time`/`end_time` (ISO 8601), `time_basis` (`auto|published|crawled`), `language` (ISO 639-1 list: ar, de, en, es, fr, hi, id, it, ja, ko, nl, pl, pt, ru, th, tr, vi, zh), `include_domains`/`exclude_domains`, `highlight` {enable, max_tokens}, `full_content` {enable, max_tokens}, `subjects` {enable, count 1 to 5, max_sub_news 1 to 20}. The response has `data.results[]` (title, url, highlight, authors, time_published) and `data.subjects[]` (name, summary, time_start, top_news, sub_news[]). Full reference: https://docs.octen.ai/capabilities/news-search

## Scoring

Right on a clue the house agent missed: 4. Right and faster than the house agent: 2, slower: 1. Wrong: -2. Blank: 0. The earliest article in an answer key of 3+ articles: +2 more. A clue nobody gets right (house included) scores 0 for everyone. Some clues are fakes (often a real story with one fact changed): blank scores +2, any link -2. So speed matters, every detail of the clue must be checked against the article, and answering blank beats a likely-wrong guess.

## Testing

- `uv run play.py ask "clue"` runs one clue; add `-v` to see Codex's output.
- `uv run play.py eval` runs all practice clues in parallel and scores them like the game (answer key, then judge). `--compare` diffs against the previous run in `runs/`. Use it after every change.
