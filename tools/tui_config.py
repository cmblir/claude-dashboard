#!/usr/bin/env python3
"""Terminal configurator for LazyClaude — like ``openclaw`` but stdlib only.

Run::

    python3 tools/tui_config.py

Three columns:
  • left   — section list (Providers / Slack / Telegram / Orchestrator / Status)
  • middle — items in the selected section
  • right  — detail + edit form for the selected item

Keys:
  ↑/↓ or j/k — move
  →/Enter    — drill in / edit
  ←/Esc      — back
  s          — save current edit
  t          — test connection (Slack/Telegram)
  q          — quit

The TUI never holds its own state — it reads/writes the same JSON files the
HTTP server uses (resolved through ``server.config``). That way the dashboard
and the TUI stay coherent without extra plumbing.
"""
from __future__ import annotations

import curses
import os
import sys
from pathlib import Path
from typing import Callable, Optional

# Make the project root importable when run as a script.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from server import slack_api, telegram_api, orchestrator                   # noqa: E402
from server.ai_providers import get_registry, AIResponse                   # noqa: E402


# ───────── Section model ─────────

class _State:
    def __init__(self) -> None:
        self.sections = ["Providers", "Slack", "Telegram", "Orchestrator", "Status"]
        self.section_idx = 0
        self.item_idx = 0
        self.column = 0          # 0=sections, 1=items, 2=detail
        self.input_buffer = ""
        self.input_field: Optional[str] = None
        self.message = "Ready. ?: help, q: quit"
        self.message_kind = "info"   # info | ok | err

    def set_msg(self, text: str, kind: str = "info") -> None:
        self.message = text
        self.message_kind = kind


def _items_for(state: _State) -> list[tuple[str, dict]]:
    """Returns (label, payload) for each item in the active section."""
    sec = state.sections[state.section_idx]
    if sec == "Providers":
        out: list[tuple[str, dict]] = []
        for p in get_registry().all_providers():
            avail = "✓" if p.is_available() else "·"
            out.append((f"[{avail}] {p.provider_id} ({p.provider_type})",
                        {"providerId": p.provider_id}))
        return out
    if sec == "Slack":
        cfg = slack_api.load_slack_config()
        return [
            (f"Token: {('set ('+cfg['token'][:6]+'…)') if cfg.get('token') else 'not set'}",
             {"field": "token"}),
            (f"Default channel: {cfg.get('defaultChannel') or '(none)'}",
             {"field": "defaultChannel"}),
            ("Test connection", {"action": "slack_test"}),
            ("Clear config", {"action": "slack_clear"}),
        ]
    if sec == "Telegram":
        cfg = telegram_api.load_telegram_config()
        return [
            (f"Token: {('set ('+cfg['token'][:6]+'…)') if cfg.get('token') else 'not set'}",
             {"field": "token"}),
            (f"Default chat: {cfg.get('defaultChat') or '(none)'}",
             {"field": "defaultChat"}),
            (f"Mode: {cfg.get('mode')}",  {"field": "mode"}),
            ("Test connection", {"action": "tg_test"}),
            ("Clear config", {"action": "tg_clear"}),
        ]
    if sec == "Orchestrator":
        cfg = orchestrator.load_config()
        rows: list[tuple[str, dict]] = [
            (f"Planner: {cfg['plannerAssignee']}",            {"field": "plannerAssignee"}),
            (f"Aggregator: {cfg['aggregatorAssignee']}",      {"field": "aggregatorAssignee"}),
            (f"Defaults: {', '.join(cfg['defaultAssignees'])}", {"field": "defaultAssignees"}),
            (f"Max parallel: {cfg['maxParallel']}",            {"field": "maxParallel"}),
        ]
        for i, b in enumerate(cfg.get("bindings") or []):
            target = b.get("channel") or b.get("chat") or ""
            rows.append((f"Binding · {b.get('kind')} → {target}",
                         {"binding_idx": i}))
        rows.append(("+ Add binding", {"action": "add_binding"}))
        return rows
    if sec == "Status":
        cfg_orch = orchestrator.load_config()
        return [
            (f"Bindings: {len(cfg_orch.get('bindings') or [])}", {}),
            (f"Available providers: {len(get_registry().available_providers())}", {}),
            ("Press Enter to start listeners", {"action": "start_listeners"}),
        ]
    return []


# ───────── Field handlers ─────────

def _commit_text_field(section: str, field: str, value: str) -> tuple[bool, str]:
    """Apply a single-field edit. Returns (ok, message)."""
    value = value.strip()
    if section == "Slack":
        if field == "token":
            r = slack_api.api_slack_config_save({"token": value})
        elif field == "defaultChannel":
            r = slack_api.api_slack_config_save({"defaultChannel": value})
        else:
            return False, f"unknown field: {field}"
    elif section == "Telegram":
        if field in ("token", "defaultChat", "mode"):
            r = telegram_api.api_telegram_config_save({field: value or None
                                                       if field == "token" else value})
        else:
            return False, f"unknown field: {field}"
    elif section == "Orchestrator":
        cfg = orchestrator.load_config()
        if field == "defaultAssignees":
            cfg[field] = [x.strip() for x in value.split(",") if x.strip()]
        elif field == "maxParallel":
            try:
                cfg[field] = max(1, min(int(value), 16))
            except ValueError:
                return False, "must be an integer"
        else:
            cfg[field] = value
        if not orchestrator.save_config(cfg):
            return False, "save failed"
        return True, "saved"
    else:
        return False, f"section {section} not editable"
    if r.get("ok"):
        return True, "saved"
    return False, str(r.get("error") or "save failed")


def _add_binding_interactive(stdscr) -> tuple[bool, str]:
    kind = _prompt(stdscr, "Binding kind (slack/telegram/http): ")
    if not kind:
        return False, "cancelled"
    target_label = "channel" if kind in ("slack", "http") else "chat"
    target = _prompt(stdscr, f"{target_label} id: ")
    if not target:
        return False, "cancelled"
    assignees = _prompt(stdscr, "assignees (comma-separated, blank=use defaults): ")
    workflow = _prompt(stdscr, "workflowId (blank for ad-hoc): ")
    body: dict = {"kind": kind, target_label: target}
    if assignees.strip():
        body["assignees"] = [a.strip() for a in assignees.split(",") if a.strip()]
    if workflow.strip():
        body["workflowId"] = workflow.strip()
    r = orchestrator.api_orch_bind(body)
    return bool(r.get("ok")), str(r.get("error") or "bound")


def _run_action(stdscr, section: str, payload: dict, state: _State) -> None:
    action = payload.get("action")
    if action == "slack_test":
        r = slack_api.api_slack_test({})
        state.set_msg(f"slack: {r}", "ok" if r.get("ok") else "err")
    elif action == "slack_clear":
        slack_api.api_slack_config_clear({})
        state.set_msg("slack config cleared", "ok")
    elif action == "tg_test":
        r = telegram_api.api_telegram_test({})
        state.set_msg(f"telegram: {r}", "ok" if r.get("ok") else "err")
    elif action == "tg_clear":
        telegram_api.api_telegram_config_clear({})
        state.set_msg("telegram config cleared", "ok")
    elif action == "start_listeners":
        r = orchestrator.api_orch_start({})
        state.set_msg(f"listeners: {r['status']}", "ok")
    elif action == "add_binding":
        ok, msg = _add_binding_interactive(stdscr)
        state.set_msg(msg, "ok" if ok else "err")
    elif "binding_idx" in payload:
        idx = payload["binding_idx"]
        cfg = orchestrator.load_config()
        try:
            b = cfg["bindings"][idx]
        except IndexError:
            state.set_msg("binding not found", "err"); return
        action2 = _prompt(stdscr, "(d)elete binding, anything else cancels: ")
        if action2.lower().startswith("d"):
            field = "channel" if b["kind"] in ("slack", "http") else "chat"
            orchestrator.api_orch_unbind({"kind": b["kind"], field: b.get(field)})
            state.set_msg("binding removed", "ok")
    elif payload.get("field"):
        field = payload["field"]
        cur = _prompt(stdscr, f"{field}: ")
        if cur is None:
            return
        ok, msg = _commit_text_field(section, field, cur)
        state.set_msg(msg, "ok" if ok else "err")
    elif payload.get("providerId"):
        pid = payload["providerId"]
        p = get_registry().get(pid)
        if not p:
            state.set_msg("provider not found", "err"); return
        info = (f"{pid}\ntype: {p.provider_type}\n"
                f"available: {p.is_available()}\nicon: {p.icon}")
        _show_modal(stdscr, info)


# ───────── Curses primitives ─────────

def _prompt(stdscr, label: str) -> str:
    h, w = stdscr.getmaxyx()
    curses.echo()
    stdscr.move(h - 2, 0); stdscr.clrtoeol()
    stdscr.addstr(h - 2, 0, label[: w - 2])
    stdscr.refresh()
    try:
        s = stdscr.getstr(h - 2, len(label), w - len(label) - 2)
    finally:
        curses.noecho()
    return s.decode("utf-8", errors="replace") if isinstance(s, bytes) else (s or "")


def _show_modal(stdscr, text: str) -> None:
    h, w = stdscr.getmaxyx()
    box_h, box_w = min(h - 4, 12), min(w - 4, 80)
    win = curses.newwin(box_h, box_w, (h - box_h) // 2, (w - box_w) // 2)
    win.box()
    for i, line in enumerate(text.splitlines()[: box_h - 2]):
        win.addstr(1 + i, 2, line[: box_w - 4])
    win.addstr(box_h - 1, 2, " press any key ")
    win.refresh()
    win.getch()


def _draw(stdscr, state: _State) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    col1 = max(14, w // 5)
    col2 = max(28, w // 3)

    # Header
    stdscr.addstr(0, 0, " LazyClaude · TUI configurator ".ljust(w),
                  curses.A_REVERSE)

    # Section column
    for i, name in enumerate(state.sections):
        attr = curses.A_STANDOUT if i == state.section_idx and state.column == 0 \
            else (curses.A_BOLD if i == state.section_idx else curses.A_NORMAL)
        stdscr.addstr(2 + i, 1, name.ljust(col1 - 2)[: col1 - 2], attr)

    # Items column
    items = _items_for(state)
    if not items:
        stdscr.addstr(2, col1 + 1, "(no items)")
    else:
        if state.item_idx >= len(items):
            state.item_idx = 0
        for i, (label, _payload) in enumerate(items[: h - 5]):
            attr = curses.A_STANDOUT if i == state.item_idx and state.column >= 1 \
                else curses.A_NORMAL
            stdscr.addstr(2 + i, col1 + 1, label[: col2 - 2], attr)

    # Detail / hint column
    detail_x = col1 + col2 + 1
    if items:
        label, payload = items[state.item_idx]
        stdscr.addstr(2, detail_x, "Detail")
        for i, line in enumerate(_describe_payload(state, payload).splitlines()):
            stdscr.addstr(4 + i, detail_x, line[: w - detail_x - 1])

    # Footer
    msg = state.message
    attr = curses.A_BOLD
    if state.message_kind == "err":
        attr |= curses.A_REVERSE
    stdscr.addstr(h - 1, 0, msg[: w - 1].ljust(w - 1), attr)
    stdscr.refresh()


def _describe_payload(state: _State, payload: dict) -> str:
    if "providerId" in payload:
        p = get_registry().get(payload["providerId"])
        if not p:
            return "(provider missing)"
        return (f"id: {p.provider_id}\nname: {p.provider_name}\n"
                f"type: {p.provider_type}\navailable: {p.is_available()}\n\n"
                "Enter to inspect.")
    if "field" in payload:
        return f"field: {payload['field']}\n\nEnter to edit."
    if "action" in payload:
        return f"action: {payload['action']}\n\nEnter to run."
    if "binding_idx" in payload:
        cfg = orchestrator.load_config()
        try:
            b = cfg["bindings"][payload["binding_idx"]]
            return ("\n".join(f"{k}: {v}" for k, v in b.items())
                    + "\n\nEnter to delete.")
        except IndexError:
            return "(binding gone)"
    return ""


# ───────── Main loop ─────────

def _main(stdscr) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    state = _State()

    while True:
        _draw(stdscr, state)
        ch = stdscr.getch()
        if ch in (ord("q"), 27):  # q or Esc
            if state.column == 0:
                return
            state.column = max(0, state.column - 1)
            continue
        if ch in (curses.KEY_UP, ord("k")):
            if state.column == 0:
                state.section_idx = max(0, state.section_idx - 1)
                state.item_idx = 0
            else:
                state.item_idx = max(0, state.item_idx - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            if state.column == 0:
                state.section_idx = min(len(state.sections) - 1, state.section_idx + 1)
                state.item_idx = 0
            else:
                state.item_idx = min(max(0, len(_items_for(state)) - 1),
                                     state.item_idx + 1)
        elif ch in (curses.KEY_RIGHT, ord("l"), ord("\n"), 10):
            items = _items_for(state)
            if not items:
                continue
            if state.column < 2:
                state.column += 1
            label, payload = items[state.item_idx]
            section = state.sections[state.section_idx]
            _run_action(stdscr, section, payload, state)
        elif ch in (curses.KEY_LEFT, ord("h")):
            state.column = max(0, state.column - 1)
        elif ch == ord("?"):
            _show_modal(stdscr,
                        "Keys:\n"
                        "  ↑/↓ or j/k  move\n"
                        "  →/Enter      drill in / edit\n"
                        "  ←/Esc        back\n"
                        "  q            quit\n"
                        "  ?            this help\n")


def main() -> int:
    if not sys.stdout.isatty():
        print("tui_config: stdout is not a TTY — run from an interactive terminal.")
        return 2
    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
