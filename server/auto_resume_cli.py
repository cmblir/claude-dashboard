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

Output is JSON on stdout. Exit code 0 on ok, 1 on error.

The Lazyclaude HTTP server does NOT need to be running — this calls the
underlying API functions directly so the CLI works in headless setups
(CI, pre-commit hooks, ad-hoc scripts).
"""
from __future__ import annotations

import argparse
import json
import sys

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

    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
