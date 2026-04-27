"""Tiny CLI for the Auto-Resume supervisor — useful from terminal scripts.

Usage:
    python3 -m server.auto_resume_cli status
    python3 -m server.auto_resume_cli set <session_id> [--prompt P] [--poll N]
                                                       [--idle N] [--max N]
                                                       [--continue] [--hooks]
    python3 -m server.auto_resume_cli cancel <session_id>
    python3 -m server.auto_resume_cli get <session_id>
    python3 -m server.auto_resume_cli install-hooks <cwd>
    python3 -m server.auto_resume_cli uninstall-hooks <cwd>
    python3 -m server.auto_resume_cli watch <session_id> [same flags as set]

`watch` keeps the supervisor running in the foreground (no Lazyclaude
HTTP server needed). It calls `set` then blocks, printing one status
line every refresh interval. Ctrl+C stops cleanly (cancels the binding).

Output is JSON on stdout (status/get/set/cancel/install-hooks/uninstall-
hooks) or human-readable status lines (watch). Exit code 0 on ok, 1 on
error.

The Lazyclaude HTTP server does NOT need to be running — this calls the
underlying API functions directly so the CLI works in headless setups
(CI, pre-commit hooks, ad-hoc scripts, terminal-only workflows).
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time

from .auto_resume import (
    api_auto_resume_cancel, api_auto_resume_get,
    api_auto_resume_install_hooks, api_auto_resume_set,
    api_auto_resume_status, api_auto_resume_uninstall_hooks,
)


def _emit(payload: dict) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="auto_resume_cli", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    s = sub.add_parser("set")
    s.add_argument("session_id")
    s.add_argument("--prompt", default="")
    s.add_argument("--cwd", default="")
    s.add_argument("--poll", type=int, default=300)
    s.add_argument("--idle", type=int, default=90)
    s.add_argument("--max",  type=int, default=12, dest="max_attempts")
    s.add_argument("--continue", dest="use_continue", action="store_true")
    s.add_argument("--hooks", dest="install_hooks", action="store_true")

    c = sub.add_parser("cancel")
    c.add_argument("session_id")

    g = sub.add_parser("get")
    g.add_argument("session_id")

    ih = sub.add_parser("install-hooks")
    ih.add_argument("cwd")

    uh = sub.add_parser("uninstall-hooks")
    uh.add_argument("cwd")

    w = sub.add_parser("watch")
    w.add_argument("session_id")
    w.add_argument("--prompt", default="")
    w.add_argument("--cwd", default="")
    w.add_argument("--poll", type=int, default=300)
    w.add_argument("--idle", type=int, default=90)
    w.add_argument("--max",  type=int, default=12, dest="max_attempts")
    w.add_argument("--continue", dest="use_continue", action="store_true")
    w.add_argument("--hooks", dest="install_hooks", action="store_true")
    w.add_argument("--refresh", type=int, default=10, help="status print interval (seconds)")

    args = p.parse_args(argv)

    if args.cmd == "status":
        return _emit(api_auto_resume_status({}))
    if args.cmd == "set":
        return _emit(api_auto_resume_set({
            "sessionId":    args.session_id,
            "prompt":       args.prompt,
            "cwd":          args.cwd,
            "pollInterval": args.poll,
            "idleSeconds":  args.idle,
            "maxAttempts":  args.max_attempts,
            "useContinue":  args.use_continue,
            "installHooks": args.install_hooks,
        }))
    if args.cmd == "cancel":
        return _emit(api_auto_resume_cancel({"sessionId": args.session_id}))
    if args.cmd == "get":
        return _emit(api_auto_resume_get({"sessionId": [args.session_id]}))
    if args.cmd == "install-hooks":
        return _emit(api_auto_resume_install_hooks({"cwd": args.cwd}))
    if args.cmd == "uninstall-hooks":
        return _emit(api_auto_resume_uninstall_hooks({"cwd": args.cwd}))
    if args.cmd == "watch":
        return _watch(args)

    p.print_help()
    return 2


def _watch(args) -> int:
    """Foreground supervisor — sets up the binding then loops printing
    status lines until Ctrl+C, at which point it cleanly cancels."""
    set_resp = api_auto_resume_set({
        "sessionId":    args.session_id,
        "prompt":       args.prompt,
        "cwd":          args.cwd,
        "pollInterval": args.poll,
        "idleSeconds":  args.idle,
        "maxAttempts":  args.max_attempts,
        "useContinue":  args.use_continue,
        "installHooks": args.install_hooks,
    })
    if not set_resp.get("ok"):
        print("set failed:", set_resp.get("error"), file=sys.stderr)
        return 1
    sid = args.session_id
    print(f"[watch] auto-resume bound for {sid} — Ctrl+C to stop and cancel.")

    stop_flag = {"v": False}
    def _on_sigint(signum, frame):
        stop_flag["v"] = True
        print("\n[watch] received SIGINT — cancelling binding...")
    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    try:
        while not stop_flag["v"]:
            r = api_auto_resume_get({"sessionId": [sid]})
            entry = (r or {}).get("entry") or {}
            if not entry:
                print("[watch] binding disappeared, stopping")
                return 1
            ts = time.strftime("%H:%M:%S")
            line = (
                f"[{ts}] state={entry.get('state'):<10} "
                f"attempts={entry.get('attempts')}/{entry.get('maxAttempts')} "
                f"reason={entry.get('lastExitReason') or '-'} "
                f"exit={entry.get('lastExitCode')}"
            )
            stop_at = int(entry.get("nextAttemptAt") or 0)
            if stop_at:
                wait = max(0, (stop_at - int(time.time() * 1000)) // 1000)
                line += f" next-in={wait}s"
            print(line, flush=True)
            if entry.get("state") in ("done", "failed", "exhausted"):
                print(f"[watch] terminal state '{entry.get('state')}': {entry.get('stopReason') or ''}")
                return 0 if entry.get("state") == "done" else 1
            for _ in range(max(1, args.refresh)):
                if stop_flag["v"]:
                    break
                time.sleep(1)
    finally:
        api_auto_resume_cancel({"sessionId": sid})
        print("[watch] binding cancelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
