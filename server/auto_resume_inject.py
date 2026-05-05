"""Live TTY injection for Auto-Resume (macOS).

The default Auto-Resume mechanism (auto_resume.py) spawns
`claude --resume <id> -p <prompt>` as a separate subprocess. That
subprocess writes new turns to the SAME session JSONL — the data
gets injected at the file level — but the user's *live* terminal
window keeps showing whatever it was showing (e.g. a frozen
"1) Continue 2) Quit" rate-limit selection prompt).

This module fills that gap on macOS:

  Strategy A — TTY-targeted AppleScript (iTerm2, Terminal.app):
    1. Find the PID for the live Claude session
    2. Read the TTY that PID is bound to (`ps -o tty=`)
    3. Walk iTerm2 / Terminal.app windows via AppleScript to
       find the matching session
    4. `write text "..." newline 1` per keystroke

  Strategy B — System Events keystroke (Warp, kitty, alacritty,
  wezterm, anything-else):
    1. Walk the process tree from PID upward to find the bundle
       identifier of the macOS app hosting this terminal.
    2. `tell application "<X>" to activate` to bring it forward.
    3. For ASCII keystrokes (e.g. "1"): `keystroke "1"` via
       System Events, then key code 36 (Return).
    4. For the user prompt (may be Korean / Unicode): set the
       clipboard, paste with Cmd+V, then Return — this handles
       arbitrary Unicode reliably without depending on the
       active keyboard layout.
    5. Restore the original clipboard at the end.

  Strategy A is preferred when available — it's TTY-targeted
  (no race with another window) and doesn't disturb the active
  app focus. Strategy B is the fallback for terminals that don't
  publish a tty-aware AppleScript dictionary.

Why keystrokes instead of writing to /dev/ttysNNN directly:
    Writing to the slave end of a pty from a non-controlling
    process gets the bytes echoed back as input only on Linux with
    TIOCSTI ioctl, which Apple removed in macOS 10.13 for security.
    AppleScript's `write text` and System Events `keystroke` APIs
    are the supported equivalents.

Permissions:
    Strategy B requires Accessibility permission for whichever
    process invokes osascript (the dashboard's Python in our
    case). The first call surfaces a system permission prompt;
    once granted, it sticks. We surface the underlying error
    verbatim so the user can grant it manually if needed.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from .logger import log


# Known macOS terminal apps. The keys are the substrings we look for
# in the process command (case-insensitive); the values are the
# canonical app names AppleScript expects for `tell application`.
_TERMINAL_APPS_BY_CMD: list[tuple[str, str]] = [
    ("warp.app/contents/macos/stable", "Warp"),
    ("warp.app/", "Warp"),
    ("iterm.app/", "iTerm2"),
    ("iterm2.app/", "iTerm2"),
    ("terminal.app/", "Terminal"),
    ("kitty.app/", "kitty"),
    ("wezterm/", "WezTerm"),
    ("alacritty.app/", "Alacritty"),
    ("ghostty.app/", "Ghostty"),
    ("hyper.app/", "Hyper"),
    ("tabby.app/", "Tabby"),
    # VS Code's integrated terminal — System Events keystrokes still
    # work because it routes them to the focused panel.
    ("visual studio code", "Code"),
    ("vscode", "Code"),
    ("cursor.app/", "Cursor"),
]


# ───────── PID → TTY ─────────

def _tty_for_pid(pid: int) -> Optional[str]:
    """Return the TTY device the process is bound to, e.g. 'ttys001'.
    None if the process is gone OR has no controlling terminal.
    """
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "tty="],
            text=True, timeout=5,
        )
        tty = out.strip()
        # ps may return '?' or empty for daemonised / no-tty processes.
        if not tty or tty == "?" or tty == "??":
            return None
        return tty
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def _full_tty_path(short: str) -> str:
    """Normalize 'ttys001' → '/dev/ttys001'."""
    if short.startswith("/dev/"):
        return short
    return f"/dev/{short}"


# ───────── PID → terminal app ─────────

def _ppid_of(pid: int) -> Optional[int]:
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "ppid="],
            text=True, timeout=5,
        )
        s = out.strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _command_of(pid: int) -> str:
    try:
        return subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True, timeout=5,
        ).strip()
    except Exception:
        return ""


def _detect_terminal_app(pid: int, max_depth: int = 20) -> Optional[str]:
    """Walk up the process tree from `pid` and return the first
    macOS terminal app name we recognize, or None.

    Stops at depth `max_depth`, root (pid 1), or when the parent
    chain breaks. Matches by substring against `ps -o command=` —
    case-insensitive.
    """
    cur: Optional[int] = pid
    seen: set[int] = set()
    for _ in range(max_depth):
        if cur is None or cur <= 1 or cur in seen:
            return None
        seen.add(cur)
        cmd_lower = _command_of(cur).lower()
        for needle, app_name in _TERMINAL_APPS_BY_CMD:
            if needle in cmd_lower:
                return app_name
        cur = _ppid_of(cur)
    return None


# ───────── AppleScript runners ─────────

def _run_osascript(script: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Execute an AppleScript snippet via osascript.
    Returns (ok, stdout_or_error). osascript is part of macOS — if
    it's missing, we're not on macOS at all.
    """
    if shutil.which("osascript") is None:
        return False, "osascript not on PATH (not macOS?)"
    try:
        p = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "osascript failed").strip()
        return True, (p.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return False, f"osascript timed out after {timeout}s"
    except Exception as e:
        return False, f"osascript crashed: {e}"


def _escape_applescript_string(s: str) -> str:
    """Escape a string for embedding in an AppleScript double-quoted literal.
    AppleScript escapes are: \\ → \\\\, " → \\\".
    Newlines are preserved as literal — `write text` consumes them as the
    user typing newline (which we want for the trailing Return).
    """
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ───────── iTerm2 ─────────

def _iterm2_inject(target_tty: str, keystrokes: list[str]) -> tuple[bool, str]:
    """Find the iTerm session whose `tty` matches `target_tty` and
    send each item in `keystrokes` as a separate `write text` line.

    Each keystroke is sent with `newline 1` so the receiving program
    sees the line as committed (Return pressed).

    The macOS app is registered as "iTerm" in its scripting
    dictionary (despite being marketed as iTerm2). The class is
    "iTerm2" but `tell application` uses "iTerm".
    """
    target_full = _full_tty_path(target_tty)
    parts = []
    for k in keystrokes:
        esc = _escape_applescript_string(k)
        parts.append(f'write text "{esc}" newline 1')
        parts.append("delay 0.15")
    body = "\n".join(parts)
    script = f'''
on injectIntoMatchingSession(targetTTY)
    tell application "iTerm"
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if (tty of s) is targetTTY then
                        tell s
                            {body}
                        end tell
                        return "iterm:matched"
                    end if
                end repeat
            end repeat
        end repeat
    end tell
    return "iterm:no-match"
end injectIntoMatchingSession

return injectIntoMatchingSession("{target_full}")
'''
    ok, out = _run_osascript(script, timeout=8.0)
    if not ok:
        return False, f"iterm osascript failed: {out}"
    if "no-match" in out:
        return False, f"iterm: no session with tty {target_full}"
    return True, "iterm"


# ───────── Terminal.app ─────────

def _terminal_app_inject(target_tty: str, keystrokes: list[str]) -> tuple[bool, str]:
    """Same idea for Apple's bundled Terminal.app. Terminal exposes
    `tty` on tabs (not sessions). `do script "..." in <tab>` runs the
    string AS IF the user typed it, including the newline at the end.
    """
    target_full = _full_tty_path(target_tty)
    # do script appends an implicit Return when the string has no
    # trailing newline. To send Return between two strings we just
    # include the newline ourselves; AppleScript's \\n inside a
    # double-quoted string becomes a real LF when osascript runs.
    parts = []
    for k in keystrokes:
        esc = _escape_applescript_string(k)
        parts.append(f'do script "{esc}" in matchedTab')
        parts.append("delay 0.15")
    body = "\n".join(parts)
    script = f'''
on injectIntoMatchingTab(targetTTY)
    tell application "Terminal"
        repeat with w in windows
            try
                repeat with tabRef in tabs of w
                    try
                        if (tty of tabRef) is targetTTY then
                            set matchedTab to tabRef
                            {body}
                            return "terminal-app:matched"
                        end if
                    on error
                        -- ignore tab walk errors
                    end try
                end repeat
            on error
                -- ignore window walk errors
            end try
        end repeat
    end tell
    return "terminal-app:no-match"
end injectIntoMatchingTab

return injectIntoMatchingTab("{target_full}")
'''
    ok, out = _run_osascript(script, timeout=10.0)
    if not ok:
        return False, f"terminal.app osascript failed: {out}"
    if "no-match" in out:
        return False, f"terminal.app: no tab with tty {target_full}"
    return True, "terminal-app"


# ───────── System Events keystroke fallback ─────────

def _system_events_inject(app_name: str, keystrokes: list[str]) -> tuple[bool, str]:
    """Strategy B — activate the target app and send keystrokes via
    System Events. Used for terminals that don't expose a tty-aware
    AppleScript dictionary (Warp, kitty, alacritty, wezterm, IDE
    integrated terminals).

    Sequence per keystroke:
      1. Save current clipboard.
      2. Set clipboard to the keystroke text (handles arbitrary
         Unicode — the active keyboard layout doesn't matter).
      3. Paste with Cmd+V.
      4. Press Return (key code 36).
      5. Wait 150ms before the next keystroke.
      6. Restore the original clipboard.

    For pure-ASCII single chars (e.g. "1"), we still use the
    clipboard path for uniformity — slight overhead, but
    consistent semantics across the whole sequence.
    """
    if not keystrokes:
        return False, "no keystrokes to send"
    # Build the sequence of `set the clipboard / keystroke "v" cmd / key code 36`
    # blocks. We delay 0.2s before the FIRST paste so the activated
    # app has time to take focus, and 0.15s between subsequent
    # keystrokes so claude-cli can react.
    blocks = []
    for i, k in enumerate(keystrokes):
        esc = _escape_applescript_string(k)
        prefix_delay = "0.25" if i == 0 else "0.15"
        blocks.append(f'''
        delay {prefix_delay}
        set the clipboard to "{esc}"
        delay 0.05
        keystroke "v" using command down
        delay 0.10
        key code 36
        ''')
    body = "\n".join(blocks)
    app_esc = _escape_applescript_string(app_name)
    script = f'''
on injectKeystrokesViaSE(appName)
    -- Preserve the user's clipboard. On macOS, the clipboard is a
    -- single global — repeatedly setting it would clobber
    -- whatever the user had copied. Save → restore around the
    -- whole sequence.
    set savedClip to ""
    try
        set savedClip to the clipboard as text
    end try
    try
        tell application appName to activate
        delay 0.30
        tell application "System Events"
            {body}
        end tell
        return "system-events:ok"
    on error errMsg number errNum
        try
            set the clipboard to savedClip
        end try
        return "system-events:error " & errNum & " " & errMsg
    end try
    -- Restore the user's clipboard.
    try
        set the clipboard to savedClip
    end try
    return "system-events:ok"
end injectKeystrokesViaSE

return injectKeystrokesViaSE("{app_esc}")
'''
    # Tighter timeout — System Events keystroke fires fast when
    # Accessibility permission is granted; the only thing that
    # makes it slow is a permission prompt blocking on the user.
    # If we hang past 6s+overhead, surface the well-known cause
    # rather than waiting forever.
    ok, out = _run_osascript(script, timeout=6.0 + 0.4 * len(keystrokes))
    perm_hint = (
        "Open System Settings → Privacy & Security → Accessibility and "
        "enable the entry for python3 / Python.app (or whatever process "
        "is running the dashboard). On the first call you may also see a "
        "system dialog — if you missed it, the toggle in Settings is the "
        "permanent fix."
    )
    if not ok:
        if "timed out" in out.lower():
            return False, (
                f"system-events osascript timed out — most likely the dashboard's "
                f"Python is missing Accessibility permission. {perm_hint} "
                f"Original: {out}"
            )
        return False, f"system-events osascript failed: {out}"
    if out.startswith("system-events:error"):
        # Common error codes:
        #   -1719 / 1002: not allowed to send keystrokes (Accessibility denied)
        #   -1728:        target app not found / not running
        #   -1712:        AppleEvent timeout (target app slow)
        if "1002" in out or "-1719" in out:
            return False, (
                f"{out} — Accessibility permission denied. {perm_hint}"
            )
        return False, out
    return True, f"system-events:{app_name}"


# ───────── Main entrypoint ─────────

def inject_live(
    pid: int,
    prompt: str,
    *,
    press_choice: Optional[str] = "1",
    allow_system_events: bool = True,
) -> dict:
    """Best-effort live keystroke injection into the terminal that
    hosts the given PID.

    Args:
        pid: PID of the running `claude` process.
        prompt: User-supplied text to inject. Gets a trailing
                Return (so claude's input-line submits).
        press_choice: If set (default '1'), this character is
                injected FIRST as its own line — used to dismiss
                rate-limit / login selection prompts before the
                real prompt arrives. Pass None to skip.
        allow_system_events: When Strategy A (TTY-targeted
                AppleScript for iTerm2 / Terminal.app) doesn't
                match, fall back to Strategy B (System Events
                keystrokes targeting whichever terminal app
                appears in the PID's process ancestry). Defaults
                to True. Set False to disable the fallback if
                the user worries about disturbing focus.

    Returns:
        {
          "ok": bool,
          "mechanism": str|None,   # "iterm" / "terminal-app" /
                                   # "system-events:<App>" / None
          "tty": str|None,
          "terminalApp": str|None, # App detected via process tree
          "tried": [<labels>],
          "error": str|None,
        }
    """
    if shutil.which("osascript") is None:
        return {
            "ok": False, "mechanism": None, "tty": None, "terminalApp": None,
            "tried": [],
            "error": "osascript not on PATH (live injection requires macOS)",
        }
    tty_short = _tty_for_pid(pid)
    if not tty_short:
        return {
            "ok": False, "mechanism": None, "tty": None, "terminalApp": None,
            "tried": [],
            "error": f"could not resolve TTY for pid {pid} (process gone or no controlling terminal)",
        }
    # Build the keystroke list: optional choice + the prompt itself.
    keys: list[str] = []
    if press_choice:
        keys.append(str(press_choice))
    keys.append(prompt)
    tty_full = _full_tty_path(tty_short)
    tried: list[str] = []
    last_err = ""

    # Detect the hosting terminal app upfront — used both to decide
    # whether to bother with Strategy A (skip if we already know the
    # terminal isn't iTerm/Terminal.app) and as the target for
    # Strategy B.
    detected_app = _detect_terminal_app(pid)

    # Strategy A: TTY-targeted AppleScript. Doesn't disturb focus,
    # exact match against `tty of <session>`. Skip the per-app
    # probe when the detected terminal already shows it's not
    # one of these — saves a multi-second AppleScript walk that
    # would only fail.
    apple_script_strategies: list[tuple] = []
    if detected_app in (None, "iTerm2", "iTerm"):
        apple_script_strategies.append((_iterm2_inject, "iterm"))
    if detected_app in (None, "Terminal"):
        apple_script_strategies.append((_terminal_app_inject, "terminal-app"))
    for fn, label in apple_script_strategies:
        tried.append(label)
        try:
            ok, msg = fn(tty_short, keys)
        except Exception as e:
            ok, msg = False, f"{label} crashed: {e}"
        if ok:
            log.info("auto_resume.inject_live: success via %s into %s", msg, tty_full)
            return {
                "ok": True, "mechanism": msg, "tty": tty_full,
                "terminalApp": msg.split(":", 1)[0],
                "tried": tried, "error": None,
            }
        last_err = msg
        log.info("auto_resume.inject_live: %s did not match (%s)", label, msg)

    # Strategy B: System Events fallback.
    if not allow_system_events:
        return {
            "ok": False, "mechanism": None, "tty": tty_full,
            "terminalApp": detected_app, "tried": tried,
            "error": (f"no AppleScript-tty match for {tty_full}; "
                      f"System Events fallback disabled (allow_system_events=False)"),
        }
    if not detected_app:
        return {
            "ok": False, "mechanism": None, "tty": tty_full,
            "terminalApp": None, "tried": tried,
            "error": (f"no AppleScript-tty match for {tty_full} and could not detect "
                      f"a terminal app in the process ancestry"),
        }
    tried.append(f"system-events:{detected_app}")
    try:
        ok, msg = _system_events_inject(detected_app, keys)
    except Exception as e:
        ok, msg = False, f"system-events crashed: {e}"
    if ok:
        log.info("auto_resume.inject_live: success via %s into %s", msg, tty_full)
        return {
            "ok": True, "mechanism": msg, "tty": tty_full,
            "terminalApp": detected_app, "tried": tried, "error": None,
        }
    last_err = msg
    return {
        "ok": False, "mechanism": None, "tty": tty_full,
        "terminalApp": detected_app, "tried": tried,
        "error": (f"all strategies failed for {tty_full} (terminal: {detected_app}); "
                  f"last attempt: {last_err}"),
    }
