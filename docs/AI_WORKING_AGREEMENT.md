# AI working agreement

- Read [AGENTS.md](../AGENTS.md) for competition rules and [CONTEXT.md](../CONTEXT.md) for current behavior and validation. Use the [README](../README.md) for local setup and the [event guide](event-guide.md) for the game commands.
- Treat the practice score as the acceptance metric for agent changes. Record a starter run, change one part of the agent at a time, and compare equivalent practice clues and settings before claiming an improvement. Keep saved evals in `runs/`.
- Use the existing Octen proxy and the normal agent entry points. Keep credentials private. Live competition submissions require a separate request.

## Expanded synthetic benchmark

Before measuring the expanded benchmark, the independent judge set the following acceptance criteria for the 50 cases:

- Keep 35 development and 15 holdout cases. Freeze the prompt and runner before holdout evaluation, and use development cases for tuning. Withhold individual holdout failures from tuning.
- Award six accuracy points for 45–46 correct, or seven for at least 47. Require at least 14 of 15 holdout cases correct. A positive case requires an expected article and a supported English summary. A negative case requires an empty card.
- Award one point each for median answer time at most 15.3 seconds and p90 at most 25 seconds. Award one point for 50 startup readings with p90 at most two seconds. Startup measures launch to the first `thread.started` event.
- Require at least 9/10, fully blank cards for explicit fakes, required languages on submitted local articles, one or two search attempts per case, and no incorrect links, timeouts, or refused search attempts. Any fixture with an intentional transport failure must declare its exception in advance.
- Keep fixture expectations separate from model input. Serve synthetic retrieval through an isolated loopback proxy. Check the final version on the existing 15-clue practice round, including Singapore, Indonesia, and both fakes.
