# Scoop Wars context

## Current behavior in this checkout

`ask`, `eval`, and `play` pass `prompt.md` to a fresh `codex exec` process for each clue. The prompt allows up to two adaptive `news_search` calls through the existing Octen proxy and requires at least one, including for blank cards. It uses native terms and a `zh` or `id` filter for likely local stories. Source language is inferred from the clue text. Practice language labels are available to the scorer.

The prompt asks for evidence of the exact event, its publication time, and decisive details. A materially contradictory or unverified result yields empty strings for `url` and `summary`. A matching link gets a one-sentence English summary. Live judging and submission use the existing game contracts.

The second search targets the missing evidence when the first results suggest a likely match. When the first results show no clear lead, the prompt uses a shorter query focused on the place and action or topic, keeps the local language filter where applicable, and asks for up to 20 results. Exact figures remain part of verification even when omitted from that query. The tool can return full text for up to four distinct articles to help check details missing from highlights. For a daily search, it requests published-time results and removes articles with comparable timestamps outside the rolling 24-hour interval ending now. The agent still checks when a report with missing or ambiguous metadata was published.

Eval logs measure Codex launch to its first `thread.started` event separately from search and end-to-end times. The launch marker measures process initialization to thread creation. It does not establish tool readiness or time to first search.

## Practice evidence from November 18, 2026

The setup check passed. The full practice eval ran for the starter and revised prompts using the same 15 practice clues from the game server, the same local model settings, and four parallel clues per run. The practice scorer includes correct blank responses to fake clues in its right-answer count.

| Result | Starter | Revised |
| --- | ---: | ---: |
| Estimated game points | +10 | +35 |
| Right | 8/15 | 12/15 |
| Fake clues correctly left blank | 0/2 | 2/2 |
| Local-language clues right | 3/7 | 6/7 |
| Wrong links | 5 | 0 |
| Successful News Search calls | 30 | 20 |
| Timeouts | 0 | 0 |

One of the starter's right answers became a blank. A second blank persisted, and one wrong-language link became a blank. The saved practice logs are `runs/eval-20261118-194345.json` and `runs/eval-20261118-194510.json`.

### Second-search follow-up

Three full retests used the same 15 practice clues and eval settings. The +35 run left the Ontario strike mandate (`p-en6`), the Singapore chip export-control meeting (`p-zh6`), and the Doha football friendly (`p-en7`) blank. Shorter diagnostic Octen queries surfaced the expected Ontario and Singapore articles without incorporating article names or URLs into the prompt.

| Prompt trial | Points | Earlier misses recovered | Practice log |
| --- | ---: | --- | --- |
| Change terms based on first results | +31 | Doha friendly | `runs/eval-20261118-195016.json` |
| Broaden the query when there is no clear lead | +38 | Ontario strike mandate | `runs/eval-20261118-195145.json` |
| Require more evidence before reusing details from the first results | +32 | Ontario strike mandate and Doha friendly | `runs/eval-20261118-195308.json` |

The +38 version was retained after those trials. It kept 12/15 right overall. Its local-language hits fell from 6/7 to 5/7 when the Indonesian minibus clue changed from right to blank. The Singapore clue stayed blank in all three trials. Every retest left both fake cards blank after News Search and scored +2 on each. All three retests had zero wrong links and zero timeouts. These scores are single runs per version with live search results and model output. Live round performance has yet to be measured.

### Singapore and Indonesian follow-up

Replaying a prior Singapore query returned both keyed Chinese articles at the top. The articles verified both officials, the export controls, and the agreement to explore continued access. One described the minister traveling to the US and did not specify the meeting format, while the clue called the US official visiting. The prompt allows incidental visit wording to remain unconfirmed when the participants, topic, and outcome independently identify the event. Explicit, decisive location, direction, identity, quantity, and outcome checks still apply. The Indonesian report's full text confirmed the Rp100,000 denomination separately from the aggregate, and the two officers at a coffee stall. Its highlights omitted those details.

The reference was fetched from Hieu's fork at `1f2bdb226b1c8660b8b1acf06b8a89717e11d118`. Its implementation uses parallel searches and fuller text. This checkout uses published-time search and bounded article text from that approach with adaptive queries, an English default for other stories, and a preference for original dated reports. The initial candidate's full round scored +38 with 13 right, one blank, and one unverified mirror. The next full round resolved the mirror case with the source-selection and routing changes.

| Full practice result | Hieu reference | Earlier revision |
| --- | ---: | ---: |
| Estimated points | +35 | +42 |
| Right | 14/15 | 14/15 |
| Local-language clues right | 6/7 | 7/7 |
| Fake clues that scored +2 | 2/2 | 2/2 |
| Successful News Search calls | 30 | 21 |
| Answer median / p90 | 17.8 / 20.9 s | 13.6 / 21.4 s |
| Codex launch median / p90 | 0.137 / 0.377 s | 0.151 / 0.218 s |

Both target clues matched their localized answer keys in `runs/eval-20261118-200545.json`. Both fake cards contained empty URLs and summaries after a successful News Search. There were zero wrong links, unsure verdicts, timeouts or search-budget violations. The one blank was the art auction clue. The Hieu reference log and launch measurements are in `runs/.goal-hieu/`. Both full comparisons used the same 15 clues and four concurrent workers. Timing percentiles use nearest rank for p90. Seven offline tests passed, covering launch telemetry, timeout recovery, partial logs, language propagation, and bounded evidence. Live round performance remains unmeasured.

The independent judge rated this version 10/10 against the predeclared accuracy, answer-time, and startup thresholds. It verified both target summaries, both empty fake cards, the 15-clue cohort, and the tested file hashes. The judge rating is separate from estimated game points.

### Expanded edge-case benchmark

`tests/fixtures/expanded-practice.json` contains 50 authored cases across 10 categories. A code-only temporary checkout runs the normal agent against a loopback proxy that serves the fixture evidence. Real Codex calls generate the cards. The model sees the clue and returned articles. The scorer retains the expected URLs and summary checks. Timing includes Codex model calls and excludes production Octen network latency.

The first full benchmark found two development misses. A Malaysian story was routed to Chinese, and a stale exact match was submitted. The prompt now requires grounding the country before choosing an Indonesian or Chinese language filter. English is the default outside the defined markets. Daily retrieval also enforces publication freshness on both direct articles and articles in story groups when their timestamps can be compared.

| Synthetic result | Previous | Revised |
| --- | ---: | ---: |
| Passed | 46/50 | 49/50 |
| Development passed | 33/35 | 35/35 |
| Holdout passed | 13/15 | 14/15 |
| Explicit fakes passed | 13/13 | 13/13 |
| Answer median / p90 | 11.27 / 14.83 s | 11.41 / 14.30 s |
| Codex launch median / p90 | 0.125 / 0.473 s | 0.119 / 0.522 s |

`runs/expanded-baseline.json` and `runs/expanded-candidate-v1.json` contain the comparable runs with four workers and the same fixture SHA-256. The revised run recorded 50 startup samples. Fourteen offline tests passed with zero skips or failures.

The independent judge awarded the first expanded candidate 10/10 on the synthetic cases. It accepted a correct currency amount that the raw scorer missed in both runs because the number was attached to its currency prefix. On the same adjudication rule, the previous run was 47/50 and the first expanded candidate was 50/50, including a 15/15 holdout. The previous run still failed the freshness gate with two out-of-window links. Both raw results and the frozen fixtures are retained.

Two full live reruns of the first expanded candidate both scored +35 even though both target clues and fake cards passed. Both runs searched in English twice for a Taiwan ambulance incident with no explicit location. A focused proxy check found keyed reports with native Chinese search terms. The current prompt allows that second-search fallback when the clue describes a local event without a grounded country and the English results have no plausible lead. The first search still follows grounded country routing.

The fallback passed the independent live gate with 15/15 and +44 in `runs/eval-20261118-202302.json`. The Singapore, Indonesian, and Taiwan articles were accepted. Both fake cards were fully blank after search and earned +2 each. The median answer time was 14.1 seconds, p90 was 23.4 seconds, and the slowest answer was 26.3 seconds. Codex launch time was 0.154 seconds at the median and 0.692 seconds at p90. The same 15 clues and four workers were used throughout. Hieu's run was +35 and 17.8 seconds at the median. These are practice measurements with live retrieval and variable model outputs.

The same fallback version passed the expanded gate at 10/10. `runs/expanded-candidate-v2.json` recorded 48/50 automatically, up from 46/50 on the same fixtures. Independent review applied the same currency-notation correction to both runs and scored 49/50 versus 47/50, with all 15 holdouts and all 13 explicit fakes passing. The one substantive miss was a local cafeteria clue that would have benefited from a second English query. The fallback tried Chinese and returned an empty card. Synthetic answer time was 11.59 seconds median and 14.63 seconds p90. All 50 startup readings were recorded with a 0.118-second median and a 0.168-second p90. The earlier expanded candidate scored one more on the synthetic set and fell below the live points threshold in both reruns.

### Final three practice repeats and public evidence

Three subsequent full practice runs on November 18 used the same 15 clue IDs as the starter and +44 run. The median repeat score was +40. The 15/15 practice run displayed in the [dashboard capture](docs/images/practice-dashboard.jpg) preceded these repeats. There is no verified tournament placing in the available evidence.

| Saved practice log | Right | Estimated points | Successful searches | Median answer | Eligible real clues left blank |
| --- | ---: | ---: | ---: | ---: | --- |
| `eval-20261118-204114.json` | 14/15 | +40 | 22 | 16.3 s | Art auction |
| `eval-20261118-204222.json` | 14/15 | +40 | 23 | 16.7 s | Art auction |
| `eval-20261118-204336.json` | 13/15 | +38 | 24 | 16.3 s | Ontario strike mandate, art auction |

Each repeat returned seven correct local-language articles and two correctly empty fake cards, with zero wrong links, refused calls or timeouts. The [case audit](outputs/showcase/practice-results.xlsx) covers the starter, the +44 run, and those three repeats. It links to the submitted articles and retains blanks and verdicts. The [README](README.md) shows the measured outcome and credits the upstream dashboard and reference implementation. Historical event instructions are in the [event guide](docs/event-guide.md).

For publication, the agent, fixture, runner and test files matched the recorded final benchmark hashes. The full offline suite passed all 14 tests. The source for the practice measurements is the saved November 18 runs. The configured event server was unreachable during the November 21 verification.
