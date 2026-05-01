#!/usr/bin/env python3
"""Ralph loop CLI — same-prompt iteration over the wire.

Standalone entry point for the engine in ``server/ralph.py``. No new deps,
stdlib only. Designed for two flows:

1. **In-process** (default): import the engine, run synchronously, stream
   progress to stdout. Used by developers iterating locally.
2. **Remote** (``--server URL``): POST to a running dashboard's
   ``/api/ralph/start`` and tail ``/api/ralph/status`` until the loop ends.

Examples::

    # Pass the prompt inline
    python3 tools/ralph_loop.py "Fix every failing test in this repo. \
Output <promise>DONE</promise> when green."

    # Or read from a file (the canonical Ralph pattern)
    python3 tools/ralph_loop.py --prompt-file PROMPT.md \
        --max 30 --completion '<promise>DONE</promise>' \
        --budget-usd 5

    # Talk to a running dashboard instead of importing the engine
    python3 tools/ralph_loop.py --prompt-file PROMPT.md \
        --server http://127.0.0.1:8080

Ctrl+C requests a graceful cancel — the engine stops at the next iteration
boundary rather than mid-call, preserving on-disk consistency.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Project root for local-mode import
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    sys.stderr.write("ralph_loop: prompt required (positional, --prompt-file, "
                     "or pipe via stdin)\n")
    sys.exit(2)


def _post_json(url: str, body: dict, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _run_remote(args: argparse.Namespace, prompt: str) -> int:
    base = args.server.rstrip("/")
    body = {
        "prompt":         prompt,
        "assignee":       args.assignee or "",
        "maxIterations":  args.max,
        "completion":     args.completion,
        "budgetUsd":      args.budget_usd,
        "systemPrompt":   args.system_prompt or "",
        "cwd":            args.cwd or "",
    }
    r = _post_json(f"{base}/api/ralph/start", body)
    if not r.get("ok"):
        sys.stderr.write(f"start failed: {r.get('error')}\n")
        return 1
    rid = r["runId"]
    print(f"started {rid} (max={r['maxIter']}, budget=${r['budgetUsd']:.2f}, "
          f"completion={r['completion']!r})", flush=True)

    def _cancel(*_a):
        print("\n[interrupt] cancelling…", flush=True)
        try:
            _post_json(f"{base}/api/ralph/cancel", {"runId": rid})
        except Exception as e:
            sys.stderr.write(f"cancel failed: {e}\n")

    signal.signal(signal.SIGINT, _cancel)

    last_iter_seen = -1
    while True:
        try:
            s = _get_json(f"{base}/api/ralph/status?runId={rid}")
        except urllib.error.URLError as e:
            sys.stderr.write(f"status query failed: {e}\n"); return 1
        run = s.get("run") or {}
        if run.get("iterations", 0) - 1 > last_iter_seen:
            details = run.get("iterationsDetail") or []
            for it in details:
                if it["idx"] > last_iter_seen:
                    print(f"  iter {it['idx']:3d} [{it['status']}] "
                          f"cost=${it['costUsd']:.4f} "
                          f"{(it['output'] or '')[:80]!r}", flush=True)
                    last_iter_seen = it["idx"]
        st = run.get("status")
        if st and st != "running":
            print(f"\nfinished: {st}  iterations={run.get('iterations')}  "
                  f"costUsd={run.get('costUsd'):.4f}", flush=True)
            if run.get("error"):
                print(f"error: {run['error']}", flush=True)
            return 0 if st == "done" else 1
        time.sleep(args.poll)


def _run_local(args: argparse.Namespace, prompt: str) -> int:
    from server import ralph as _ralph        # noqa: E402

    started = _ralph.start(
        prompt=prompt,
        assignee=args.assignee or "",
        max_iterations=args.max,
        completion_promise=args.completion,
        budget_usd=args.budget_usd,
        system_prompt=args.system_prompt or "",
        cwd=args.cwd or "",
    )
    if not started.get("ok"):
        sys.stderr.write(f"start failed: {started.get('error')}\n"); return 1
    rid = started["runId"]
    print(f"started {rid} (max={started['maxIter']}, "
          f"budget=${started['budgetUsd']:.2f}, "
          f"completion={started['completion']!r})", flush=True)

    def _cancel(*_a):
        print("\n[interrupt] cancelling…", flush=True)
        _ralph.cancel(rid)

    signal.signal(signal.SIGINT, _cancel)

    last_iter_seen = -1
    while True:
        s = _ralph.status(rid)
        if s is None:
            sys.stderr.write("status: not found\n"); return 1
        details = s.get("iterationsDetail") or []
        for it in details:
            if it["idx"] > last_iter_seen:
                print(f"  iter {it['idx']:3d} [{it['status']}] "
                      f"cost=${it['costUsd']:.4f} "
                      f"{(it['output'] or '')[:80]!r}", flush=True)
                last_iter_seen = it["idx"]
        if s["status"] != "running":
            print(f"\nfinished: {s['status']}  iterations={s['iterations']}  "
                  f"costUsd={s['costUsd']:.4f}", flush=True)
            if s.get("error"):
                print(f"error: {s['error']}", flush=True)
            return 0 if s["status"] == "done" else 1
        time.sleep(args.poll)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ralph_loop",
                                description="Ralph Wiggum same-prompt loop runner.")
    p.add_argument("prompt", nargs="?", default="",
                   help="Inline prompt text (or use --prompt-file / stdin).")
    p.add_argument("--prompt-file", help="Path to PROMPT.md.")
    p.add_argument("--max", type=int, default=25,
                   help="Maximum iterations (server caps at 200).")
    p.add_argument("--completion", default="<promise>DONE</promise>",
                   help="Exact string the model emits to end the loop.")
    p.add_argument("--budget-usd", type=float, default=5.0,
                   help="Cumulative cost ceiling in USD.")
    p.add_argument("--assignee", default="",
                   help='Provider:model, e.g. "claude:sonnet" or "openai:gpt-4.1".')
    p.add_argument("--system-prompt", default="")
    p.add_argument("--cwd", default="",
                   help="Working directory (passed to provider where supported).")
    p.add_argument("--server", default="",
                   help="If set, talk to a running dashboard at this URL "
                        "instead of importing the engine in-process.")
    p.add_argument("--poll", type=float, default=1.0,
                   help="Status poll interval (seconds).")
    args = p.parse_args(argv)

    prompt = _read_prompt(args)
    if not prompt.strip():
        sys.stderr.write("ralph_loop: empty prompt\n"); return 2

    if args.server:
        return _run_remote(args, prompt)
    return _run_local(args, prompt)


if __name__ == "__main__":
    sys.exit(main())
