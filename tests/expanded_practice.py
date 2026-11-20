"""Run the agent against a local Octen fixture proxy using real Codex invocations."""

import argparse
import copy
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "expanded-practice.json"
AGENT_FILES = ("play.py", "octen_client.py", "news_search_mcp.py", "card.schema.json", "prompt.md")
FIXTURE_KEY = "synthetic-practice-only"
SEARCH_LIMIT = 2


def load_fixture(raw: bytes) -> list[dict]:
    fixture = json.loads(raw)
    if fixture.get("version") != 1 or not isinstance(fixture.get("cases"), list) or not fixture["cases"]:
        raise ValueError("expected a version 1 benchmark with cases")
    seen = set()
    for case in fixture["cases"]:
        case_id = case["id"]
        if case_id in seen or case["split"] not in ("development", "holdout") or not case["clue"].strip():
            raise ValueError(f"invalid or duplicate case {case_id}")
        seen.add(case_id)
        if not 1 <= len(case["searches"]) <= SEARCH_LIMIT:
            raise ValueError(f"invalid search fixture count for {case_id}")
        urls = list(case["expected"]["urls"])
        for step in case["searches"]:
            urls.extend(article["url"] for article in response_articles(step["response"]) if article.get("url"))
        for url in urls:
            host = urlsplit(url).hostname or ""
            if not host.endswith((".example", ".test")):
                raise ValueError(f"expected a reserved synthetic article domain for {case_id}")
    return fixture["cases"]


def matches_search(match: dict, request: dict) -> bool:
    query = request.get("query", "").casefold()
    return (
        ("language" not in match or match["language"] == request.get("language"))
        and ("full_content" not in match or match["full_content"] == bool((request.get("full_content") or {}).get("enable")))
        and ("query_any" not in match or any(word.casefold() in query for word in match["query_any"]))
    )


def response_articles(response: dict):
    data = response.get("data") or {}
    yield from data.get("results") or []
    for subject in data.get("subjects") or []:
        if subject.get("top_news"):
            yield subject["top_news"]
        yield from subject.get("sub_news") or []


def fixture_payload(response: dict, full_content: bool, now: datetime) -> dict:
    payload = copy.deepcopy(response)
    for article in response_articles(payload):
        age = article.pop("published_age_minutes", None)
        article["time_published"] = None if age is None else (now - timedelta(minutes=age)).isoformat()
        if not full_content:
            article.pop("full_content", None)
    return payload


class FixtureProxy(ThreadingHTTPServer):
    def __init__(self, cases: list[dict]):
        super().__init__(("127.0.0.1", 0), FixtureRequest)
        self.tokens = {case["id"]: secrets.token_urlsafe(24) for case in cases}
        self.scripts = {self.tokens[case["id"]]: case["searches"] for case in cases}
        self.calls = {case["id"]: [] for case in cases}
        self.case_ids = {token: case_id for case_id, token in self.tokens.items()}
        self.lock = threading.Lock()

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def reply(self, token: str, path: str, request: dict) -> tuple[int, dict]:
        with self.lock:
            calls = self.calls[self.case_ids[token]]
            index = len(calls)
            script = self.scripts[token]
            step = script[index] if index < len(script) else None
            matched = step is not None and matches_search(step.get("match", {}), request)
            full_content = bool((request.get("full_content") or {}).get("enable"))
            if index >= SEARCH_LIMIT:
                status, payload = 429, {"code": 429, "msg": "Fixture search budget used"}
            elif path != "/octen/news-search":
                status, payload = 403, {"code": 403, "msg": "Only News Search is available"}
            elif matched:
                status = step.get("http_status", 200)
                payload = fixture_payload(step["response"], full_content, datetime.now(timezone.utc))
            else:
                status, payload = 200, {"data": {"results": [], "subjects": []}}
            success = status == 200 and not payload.get("code") and path == "/octen/news-search"
            calls.append({
                "attempt": index + 1, "path": path, "query": request.get("query"), "language": request.get("language"),
                "full_content": full_content, "time_range": request.get("time_range"), "time_basis": request.get("time_basis"),
                "fixture_step_available": step is not None, "matched_fixture": matched,
                "status": status, "code": payload.get("code"), "success": success,
            })
            return status, payload


class FixtureRequest(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        token = self.headers.get("x-scoop-token", "")
        if token not in self.server.scripts or self.headers.get("x-api-key") != FIXTURE_KEY:
            self.respond(403, {"code": 403, "msg": "Synthetic authentication required"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size < 65536:
                raise ValueError("invalid body size")
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict) or not isinstance(request.get("query"), str):
                raise ValueError("invalid query")
        except (ValueError, UnicodeError):
            self.respond(400, {"code": 400, "msg": "Invalid fixture request"})
            return
        self.respond(*self.server.reply(token, self.path, request))

    def respond(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass


def worker_environment(origin: str, token: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("OCTEN_", "SCOOP_"))}
    local_config = ROOT / ".env"
    if local_config.exists():
        for line in local_config.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() in {"CODEX_BIN", "CODEX_MODEL", "CODEX_REASONING"}:
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    env.update(SCOOP_SERVER=origin, SCOOP_TOKEN=token, OCTEN_API_KEY=FIXTURE_KEY, SCOOP_SEARCH_BUDGET=str(SEARCH_LIMIT))
    return env


def read_worker_events(fd, launched, startup, stop, _verbose, tools):
    with os.fdopen(fd, encoding="utf-8", errors="replace") as events:
        for line in events:
            received = time.monotonic()
            if stop.is_set():
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "thread.started" and not startup:
                startup.append(round(received - launched, 3))
            if event.get("type") != "item.started":
                continue
            item = event.get("item") or {}
            kind = item.get("type")
            if kind == "mcp_tool_call":
                tools.append(f"{item.get('server')}.{item.get('tool')}")
            elif kind in {"command_execution", "file_change", "web_search", "dynamic_tool_call", "collab_tool_call"}:
                tools.append(kind)


def run_worker(staged: Path, timeout: float) -> None:
    from dataclasses import asdict

    origin = os.environ["SCOOP_SERVER"]
    if not re.fullmatch(r"http://127\.0\.0\.1:[1-9]\d{0,4}", origin) or os.environ.get("OCTEN_API_KEY") != FIXTURE_KEY:
        raise RuntimeError("worker refuses any non-synthetic search route")
    if (staged / ".env").exists() or (staged / ".scoop.json").exists():
        raise RuntimeError("worker refuses a runner directory with local credentials")
    # The isolated worker imports the same production modules from the staged snapshot.
    sys.path.insert(0, str(staged))
    import play

    original_command = play.codex_command

    def command(workdir, output, search_log):
        args = original_command(workdir, output, search_log)
        prefix = "mcp_servers.octen.env="
        indices = [i for i, arg in enumerate(args) if arg.startswith(prefix)]
        if len(indices) != 1:
            raise RuntimeError("cannot isolate the staged agent's Octen environment")
        env = {name: os.environ[name] for name in ("SCOOP_SERVER", "SCOOP_TOKEN", "OCTEN_API_KEY", "SCOOP_SEARCH_BUDGET")}
        env.update(SCOOP_RUN_LOG=search_log, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
        args[indices[0]] = prefix + "{" + ", ".join(f"{key}={json.dumps(value)}" for key, value in env.items()) + "}"
        args[-1:-1] = ["--disable", "shell_tool", "--disable", "unified_exec"]
        return args

    tools = []
    play.codex_command = command
    play._read_codex_events = partial(read_worker_events, tools=tools)
    card = play.run_agent(sys.stdin.read(), timeout=timeout)
    print(json.dumps({"card": asdict(card), "tools": tools}, ensure_ascii=True))


def normalize_fact(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"(?<=\d)[,.\u00a0](?=\d{3}\b)", "", value)
    return " " + re.sub(r"[^\w]+", " ", value).strip() + " "


def matches_fact(fact: str, normalized_summary: str) -> bool:
    words = normalize_fact(fact).strip()
    # Fixtures use deliberate stems for verbal variants, and exact tokens for numbers.
    pattern = f" {words} " if re.search(r"\d", words) else words
    return bool(words and pattern in normalized_summary)


def is_one_sentence(summary: str) -> bool:
    if not re.search(r"[A-Za-z]", summary) or "\n" in summary:
        return False
    # Initialisms and common honorifics are not sentence breaks.
    summary = re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m.group().replace(".", "") + ("." if m.end() == len(summary) else ""), summary)
    summary = re.sub(r"\b(?:Mr|Ms|Mrs|Dr|Prof|Gov|Sen|Rep|St|Mt)\.", lambda m: m.group()[:-1], summary)
    return len(re.findall(r"[.!?]+[”\"')]*(?=\s+\S|$)", summary)) == 1 and bool(re.search(r"[.!?][”\"')]*$", summary))


def score(case: dict, card: dict, attempts: list[dict], tools: list[str]) -> list[str]:
    expected = case["expected"]
    issues = []
    if card.get("error"):
        issues.append("agent_error")
    if not 1 <= len(attempts) <= SEARCH_LIMIT or card.get("refused"):
        issues.append("search_budget")
    successes = sum(call["success"] for call in attempts)
    if successes != len(card.get("searches", [])):
        issues.append("search_telemetry_mismatch")
    if not successes:
        if not expected.get("allow_no_success"):
            issues.append("no_successful_news_search")
        elif len(attempts) != SEARCH_LIMIT:
            issues.append("did_not_retry_failed_search")
    if any(tool != "octen.news_search" for tool in tools):
        issues.append("unexpected_tool")
    url = card.get("url", "")
    summary = card.get("summary", "")
    if not expected["urls"]:
        if url or summary:
            issues.append("expected_blank_card")
    elif not url:
        issues.append("missing_url")
    elif url not in expected["urls"]:
        issues.append("wrong_url")
    else:
        if not is_one_sentence(summary):
            issues.append("invalid_summary_sentence")
        normalized = normalize_fact(summary)
        missing = [i + 1 for i, alternatives in enumerate(expected.get("summary_facts", []))
                   if not any(matches_fact(fact, normalized) for fact in alternatives)]
        if missing:
            issues.append("missing_summary_facts:" + ",".join(map(str, missing)))
    return issues


def run_case(case: dict, proxy: FixtureProxy, staged: Path, timeout: float) -> dict:
    args = [sys.executable, str(Path(__file__).resolve()), "--worker", str(staged), str(timeout)]
    env = worker_environment(proxy.origin, proxy.tokens[case["id"]])
    try:
        result = subprocess.run(args, input=case["clue"], cwd=staged, env=env, encoding="utf-8", capture_output=True, timeout=timeout + 10)
        if result.returncode:
            raise ValueError(f"worker exited with status {result.returncode}")
        worker = json.loads(result.stdout)
        card, tools = worker["card"], worker["tools"]
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        card, tools = {"error": f"fixture worker failed: {type(error).__name__}"}, []

    with proxy.lock:
        attempts = list(proxy.calls[case["id"]])
    issues = score(case, card, attempts, tools)
    return {
        "id": case["id"], "split": case["split"], "category": case["category"], "pass": not issues,
        "clue": case["clue"], "expected": case["expected"], "issues": issues,
        "card": card, "attempts": attempts, "tools": tools,
    }


def timing(values: list[float]) -> dict:
    values = sorted(values)
    if not values:
        return {"n": 0, "p50": None, "p90": None, "max": None}
    return {"n": len(values), "p50": statistics.median(values), "p90": values[math.ceil(len(values) * 0.90) - 1], "max": values[-1]}


def summarize(rows: list[dict]) -> dict:
    return {
        "total": len(rows), "passed": sum(row["pass"] for row in rows),
        "by_split": {split: {"total": sum(row["split"] == split for row in rows),
                             "passed": sum(row["split"] == split and row["pass"] for row in rows)}
                     for split in ("development", "holdout")},
        "answer_seconds": timing([row["card"]["seconds"] for row in rows if row["card"].get("seconds") is not None]),
        "startup_seconds": timing([row["card"]["codex_startup_secs"] for row in rows if row["card"].get("codex_startup_secs") is not None]),
        "first_search_seconds": timing([row["card"]["search_times"][0]["started"] for row in rows
                                        if row["card"].get("search_times") and row["card"]["search_times"][0]["started"] is not None]),
    }


def save_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        run_worker(Path(sys.argv[2]), float(sys.argv[3]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--agent-dir", type=Path, default=ROOT)
    parser.add_argument("--split", choices=("all", "development", "holdout"), default="all")
    parser.add_argument("--only", help="comma-separated case IDs for a targeted run")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=41)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / f"expanded-practice-{stamp}.json")
    args = parser.parse_args()
    if args.parallel < 1 or not math.isfinite(args.timeout) or not 0 < args.timeout <= 41:
        parser.error("parallel must be positive and timeout between zero and 41 seconds")

    raw = args.fixture.read_bytes()
    cases = [case for case in load_fixture(raw) if args.split in ("all", case["split"])]
    if args.only:
        selected = set(args.only.split(","))
        if selected - {case["id"] for case in cases}:
            parser.error("--only includes an unknown ID or a case outside --split")
        cases = [case for case in cases if case["id"] in selected]
    if not cases:
        parser.error("no cases selected")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    progress = args.output.with_suffix(".progress.json")
    rows = {}

    with tempfile.TemporaryDirectory(prefix="scoop-bench-") as scratch, FixtureProxy(cases) as proxy:
        staged = Path(scratch)
        hashes = {}
        for name in AGENT_FILES:
            path = staged / name
            shutil.copyfile(args.agent_dir / name, path)
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        server = threading.Thread(target=proxy.serve_forever, daemon=True)
        server.start()
        metadata = {
            "reference": stamp, "fixture_sha256": hashlib.sha256(raw).hexdigest(), "agent_sha256": hashes,
            "parallel": args.parallel, "timeout": args.timeout, "split": args.split,
        }
        save_json(progress, {"status": "running", "completed": 0, "selected": len(cases), **metadata})
        try:
            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                queue = {pool.submit(run_case, case, proxy, staged, args.timeout): case["id"] for case in cases}
                for future in as_completed(queue):
                    row = future.result()
                    rows[queue[future]] = row
                    counts = {"completed": len(rows), "selected": len(cases), "passing": sum(r["pass"] for r in rows.values())}
                    save_json(progress, {"status": "running", **counts, **metadata})
                    print(f"Completed {counts['completed']}/{counts['selected']} ({counts['passing']} passing)", flush=True)
        finally:
            proxy.shutdown()
            server.join()

    ordered = [rows[case["id"]] for case in cases]
    summary = summarize(ordered)
    save_json(args.output, {"version": 1, **metadata, "summary": summary, "rows": ordered})
    save_json(progress, {"status": "done", "completed": len(rows), "selected": len(cases), "summary": summary, **metadata})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
