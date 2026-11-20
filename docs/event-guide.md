# Scoop Wars event guide

## Tonight's checklist

The **event page** walks you through all of this one step at a time: join the venue Wi-Fi and open the address on the big screen. Claim your credits there first: it also shows your team (teams of 2 to 3, made by the organizers) and lets you name it. This is the same list, for you or your coding agent.

Using a coding agent? Paste this in. It runs the terminal steps and asks you for the rest.

```text
Set me up for Scoop Wars: follow "Tonight's checklist" in https://github.com/derekzaw-007/scoop-wars. Run the terminal steps yourself. Ask me for anything only I can do: Wi-Fi, the event page, logins, keys.
```

- [ ] **Create an Octen API key** on the [Octen API Platform](https://octen.ai/platform), with the account that redeemed the Octen credits.
- [ ] **Install uv, Node.js and Codex,** then log in to Codex with ChatGPT Pro.
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh   # Windows (PowerShell): powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  npm install -g @openai/codex
  codex login
  ```
- [ ] **Get the starter kit.** Your team shares one copy: one of you forks this repo and adds the others as collaborators, and everyone clones the fork. On your own, just clone it.
  ```bash
  git clone https://github.com/derekzaw-007/scoop-wars.git && cd scoop-wars   # or your team's fork
  cp .env.example .env
  ```
- [ ] **Fill in `.env`:** copy the three lines from the event page (step 7) and put your key in `OCTEN_API_KEY`. `SCOOP_SERVER` is the event page's address; `SCOOP_TOKEN` is your team's, the same for everyone on it.
- [ ] **Check your setup:** `uv run play.py doctor`. Every line should say `[ok]`, including your team's name.
- [ ] **Build.** Run `uv run play.py ui` and beat the house agent on the practice clues. Start with [where the points are](#where-the-points-are).
- [ ] **By 8:25 PM, one laptop per team runs `uv run play.py play`** and leaves it running. Hands off the keyboard from 8:30.

No uv? `pip install mcp httpx`, then use `python play.py` instead of `uv run play.py`.

## Commands

| Command                           | What it does                                                                                                  |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `uv run play.py doctor`         | Checks Python, Codex and its login, your keys, the game server, your team and a live News Search call         |
| `uv run play.py join "Team"`    | Registers a new team. Only if the help desk asks: your team and its `SCOOP_TOKEN` come from the event page. |
| `uv run play.py ask "clue"`     | Runs the agent on any clue you write. Add `-v` to watch Codex work.                                         |
| `uv run play.py eval`           | Runs every practice clue, 4 at a time, and scores them the way the game does                                  |
| `uv run play.py eval --compare` | The same, plus what changed since your last eval                                                              |
| `uv run play.py ui`             | The eval as a live dashboard in your browser, with your run history                                           |
| `uv run play.py play`           | Joins the Scoop clock. Start it by 8:25 PM, then hands off the keyboard.                                      |

## Where the points are

The house agent finds most plain clues in about 15 seconds. You won't beat it by finding the same stories the same way.

| You                                                                      | Points  |
| ------------------------------------------------------------------------ | ------- |
| Right on a clue the house agent missed                                   | 4       |
| Right, and your card came in before the house agent's                    | 2       |
| Right, but after the house agent                                         | 1       |
| Wrong                                                                    | minus 2 |
| No answer                                                                | 0       |
| **Fake clue** (describes something that didn't happen): blank card | 2       |
| **Fake clue**: any link                                            | minus 2 |

Plus 2 for linking the story's first report, and some edge cases: see [scoring details](#scoring-details).

Five ways to beat the house agent:

- **Find what it misses.** Those clues are worth 4.
- **Answer local clues in the local language.** Some clues are stories covered so far only in Chinese or Indonesian outlets, and only an article in that language counts. The house agent doesn't know this. News Search takes a `language` filter (`["zh"]`, `["id"]`); query in that language too.
- **Spot the fakes.** A fake is often a real story from today with one fact changed, so check every detail of the clue against the article and answer blank when one doesn't match.
- **Be faster** on the clues it also gets.
- **Make 2 searches count.** That's the budget per clue, all Octen search APIs combined; the game server refuses the third, and `eval` plays by the same rule.

## The eval loop

The easiest way is the dashboard:

```bash
uv run play.py ui              # opens http://localhost:8765
```

Press **Run Eval** and watch every practice clue race: your searches, your answer time, the house agent's answer time (dashed line), and the result. The tiles show what matters: how many you got right, your estimated game points, how many of the house agent's misses you got, and your median time. Click a clue to see your link, summary, searches and the judge's reason. Every run is kept on the right, with a chart of points per run; click an old run to see what changed against the one before. Each run starts a fresh process, so it always tests your latest code.

Or from the terminal:

```bash
uv run play.py eval            # a minute or two for every practice clue
# change one thing
uv run play.py eval --compare  # did it help?
```

```
clue   result    pts   time srch  house   clue text
p3     right      +2   9.8s    1  14s     A bottle of whisky from a run of only 200 ...
p7     blank      +0  41.0s    2  missed  A short-range drone that a city-state's ...
p9     wrong      -2  17.1s    2  missed  Officers found an anaesthetic being ...
       The article describes the same raid, but it was published outside the 24-hour window.

Right 9/15   Estimated game points +14   Median 16s, slowest 41s
Clues the house agent missed: you got 1/6 (4 points each)
```

- **house** is the house agent's time on that clue, or `missed`. The `missed` rows are worth 4 points each, so they're where to focus.
- **result** comes from the answer key, then the judge: the same model check the game uses for links outside the key. It reads the article and decides whether it reports the same event, was published in the last 24 hours and matches your summary. Wrong and unsure rows print the judge's reason.
- Runs are saved in `runs/`. Times run a little slower 4 at a time; use `--parallel 1` for exact timings.
- Eval JSON records Codex launch to its first `thread.started` event as `codex_startup_secs`. Each search also records its start, completion, and request duration so you can distinguish CLI startup from the time taken to reach a usable answer.
- More practice clues may unlock during the build. Run eval again when the host says so.

Run `uv run python -m unittest discover -s tests -v` for the offline runner and News Search contract tests.

### Synthetic edge cases

Run `uv run python tests/expanded_practice.py --split development` to test changes against the development cases. Run `uv run python tests/expanded_practice.py --split all` for the complete 50-case benchmark. The benchmark runs real Codex sessions through a loopback proxy that returns authored article evidence. It records case-level outcomes and timing in `runs/`. Use the live practice eval to check retrieval against the game server.

## What to change

| What            | Where                                                                                    | Why                                                                                                                                                                                                                                                     |
| --------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The search tool | `news_search_mcp.py`                                                                   | Usually the biggest win. You only get 2 calls, and each round trip costs Codex several seconds: build one precise query, set `language`, use `start_time` for "this morning", return story summaries so the agent can check details, trim the rest. |
| Codex settings  | `play.py` → `codex_command()`, or `CODEX_MODEL` / `CODEX_REASONING` in `.env` | Speed. Codex startup and reasoning take most of the 45 seconds.                                                                                                                                                                                         |
| The prompt      | `prompt.md`                                                                            | Judgment: checking every detail of the clue against the article (fakes change one fact), when to leave a clue blank, checking dates (last month's version of a story doesn't count).                                                                    |
| The whole agent | `play.py` → `run_agent()`                                                           | You can replace Codex entirely (below).                                                                                                                                                                                                                 |

News Search reference: https://docs.octen.ai/capabilities/news-search. Web Search and Octen's other single-query search APIs (Pulse, Image, Video, Business, Place) work through `octen_client.search(api, body)` and share the 2 calls per clue; see [Rules](#rules) for what's off limits.

### Replacing Codex

`run_agent(clue, timeout)` just has to return a `Card` within the timeout. Any model or framework is fine, as long as every search goes through `octen_client` (`news_search()`, or `search()` for the other Octen search APIs). That's what routes your calls through the game server so they count:

```python
import octen_client

def run_agent(clue: str, timeout: float = 41, verbose: bool = False) -> Card:
    started = time.time()
    with octen_client.capture() as searches:
        data = octen_client.news_search({"query": clue, "count": 10, "time_range": "day"})
        url, summary = pick_answer(clue, data)  # your logic, e.g. one LLM call
    return Card(url=url, summary=summary, seconds=time.time() - started, searches=list(searches))
```

`ask`, `eval` and `play` all call `run_agent()`, so they pick up your version.

## Scoring details

- **First report:** 2 more points if your article is the earliest one in the story's answer key, and the key holds at least 3 articles.
- **No News Search call:** if your team made no News Search call through the game server between the clue appearing and your card, the card scores 0, even if it's right. That includes blank cards on fake clues.
- **Nobody right:** a clue that no team gets right, the house agent included, scores 0 for everyone, wrong cards too. Fake clues always count.
- **Ties:** more right answers wins, then less total time to your right answers.

## Rules

- Search only with Octen: 2 search calls per clue, all Octen search APIs combined (a refused call doesn't count). Broad Search, Answer, Search Agent, Deep Research and Auto Search are off limits (they run many searches per call), and so are other search tools and web browsing. Extract and Embedding are fine.
- Every search goes through `octen_client`, which routes it through the game server. Octen's own MCP server, CLI or SDK skip the game server, so searches made with them don't count.
- During the Scoop clock your agent plays alone: 20 clues, about one a minute (a clue closes early once every agent has answered). A team that touches the keyboard gets a warning, then loses its next answer.
- Local clues (stories covered only in Chinese or Indonesian outlets) only accept an article in that language.
- The summary on your card is always one sentence in English, whatever language the article is in.
- If the game server goes down, the host reads the clues aloud and the game master enters your cards by hand. `play.py play` prints every card, so keep that terminal open.
