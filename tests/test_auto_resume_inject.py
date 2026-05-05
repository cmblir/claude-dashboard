"""Unit tests for server.auto_resume_inject (live TTY injection).

We can't actually drive iTerm2 / Terminal.app from pytest. Instead
we mock subprocess.run/check_output and verify:
  - PID → TTY resolution
  - AppleScript composition (the script we'd hand to osascript)
  - Mechanism order (iTerm2 first, Terminal.app fallback)
  - Press-choice + prompt keystroke list
  - Error paths (no osascript, no TTY, no matching session)
"""
from __future__ import annotations

import subprocess
import pytest

from server import auto_resume_inject as m


# ───────── _tty_for_pid ─────────

class TestTTYResolve:
    def test_returns_short_name(self, monkeypatch):
        def fake_check_output(cmd, **kw):
            assert cmd[:2] == ["ps", "-p"]
            return "ttys001\n"
        monkeypatch.setattr(subprocess, "check_output", fake_check_output)
        assert m._tty_for_pid(1234) == "ttys001"

    def test_question_mark_returns_none(self, monkeypatch):
        # Daemonised processes show '??' or '?' as their tty.
        def fake_check_output(cmd, **kw):
            return "??\n"
        monkeypatch.setattr(subprocess, "check_output", fake_check_output)
        assert m._tty_for_pid(1234) is None

    def test_empty_returns_none(self, monkeypatch):
        def fake_check_output(cmd, **kw):
            return "\n"
        monkeypatch.setattr(subprocess, "check_output", fake_check_output)
        assert m._tty_for_pid(1234) is None

    def test_subprocess_error_returns_none(self, monkeypatch):
        def fake_check_output(cmd, **kw):
            raise subprocess.SubprocessError("ps failed")
        monkeypatch.setattr(subprocess, "check_output", fake_check_output)
        assert m._tty_for_pid(1234) is None


# ───────── _full_tty_path ─────────

class TestFullTTYPath:
    def test_normalises_short(self):
        assert m._full_tty_path("ttys001") == "/dev/ttys001"

    def test_passes_full_through(self):
        assert m._full_tty_path("/dev/ttys001") == "/dev/ttys001"


# ───────── _escape_applescript_string ─────────

class TestEscape:
    def test_double_quotes_escaped(self):
        assert m._escape_applescript_string('say "hi"') == 'say \\"hi\\"'

    def test_backslashes_escaped_first(self):
        # AppleScript uses \\ to mean a literal \, so we must
        # double our own backslashes BEFORE escaping quotes.
        assert m._escape_applescript_string('a\\b') == 'a\\\\b'

    def test_newlines_to_literal(self):
        # AppleScript double-quoted strings don't tolerate raw LF;
        # \\n becomes a real LF when osascript evaluates the script.
        assert m._escape_applescript_string("a\nb") == "a\\nb"


# ───────── _run_osascript ─────────

class TestRunOsascript:
    def test_no_osascript_returns_error(self, monkeypatch):
        monkeypatch.setattr(m.shutil, "which", lambda _: None)
        ok, err = m._run_osascript("return 42")
        assert ok is False
        assert "not on PATH" in err

    def test_calls_osascript_with_script(self, monkeypatch):
        captured = {}

        class FakeProc:
            returncode = 0
            stdout = "iterm2:matched"
            stderr = ""

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            captured["kw"] = kw
            return FakeProc()
        monkeypatch.setattr(m.shutil, "which", lambda _: "/usr/bin/osascript")
        monkeypatch.setattr(subprocess, "run", fake_run)

        ok, out = m._run_osascript("script body here")
        assert ok is True
        assert out == "iterm2:matched"
        assert captured["cmd"][0:2] == ["/usr/bin/osascript", "-e"] or captured["cmd"] == ["osascript", "-e", "script body here"]
        # The script we passed must appear at index 2.
        assert captured["cmd"][2] == "script body here"
        assert captured["kw"]["capture_output"] is True

    def test_nonzero_exit_returns_error(self, monkeypatch):
        class FakeProc:
            returncode = 1
            stdout = ""
            stderr = "syntax error"

        monkeypatch.setattr(m.shutil, "which", lambda _: "/usr/bin/osascript")
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
        ok, err = m._run_osascript("bad script")
        assert ok is False
        assert "syntax error" in err


# ───────── inject_live (full flow) ─────────

class TestInjectLive:
    def _stub_environment(self, monkeypatch, tty="ttys999",
                          iterm_result=None, term_result=None,
                          se_result=None, terminal_app=None):
        """Stub everything but the keystroke composition logic so we
        can assert what we'd hand to osascript."""
        monkeypatch.setattr(m.shutil, "which", lambda name: "/usr/bin/" + name)
        monkeypatch.setattr(m, "_tty_for_pid", lambda pid: tty)
        monkeypatch.setattr(m, "_detect_terminal_app", lambda pid, **kw: terminal_app)

        captured = {"iterm2_calls": [], "terminal_calls": [], "se_calls": []}

        def fake_iterm2(target_tty, keystrokes):
            captured["iterm2_calls"].append({"tty": target_tty, "keys": list(keystrokes)})
            return iterm_result if iterm_result is not None else (True, "iterm")

        def fake_terminal(target_tty, keystrokes):
            captured["terminal_calls"].append({"tty": target_tty, "keys": list(keystrokes)})
            return term_result if term_result is not None else (True, "terminal-app")

        def fake_se(app_name, keystrokes):
            captured["se_calls"].append({"app": app_name, "keys": list(keystrokes)})
            return se_result if se_result is not None else (True, f"system-events:{app_name}")

        monkeypatch.setattr(m, "_iterm2_inject", fake_iterm2)
        monkeypatch.setattr(m, "_terminal_app_inject", fake_terminal)
        monkeypatch.setattr(m, "_system_events_inject", fake_se)
        return captured

    def test_no_osascript_short_circuits(self, monkeypatch):
        monkeypatch.setattr(m.shutil, "which", lambda _: None)
        r = m.inject_live(1234, "hello")
        assert r["ok"] is False
        assert "osascript" in (r["error"] or "")
        assert r["mechanism"] is None

    def test_no_tty_short_circuits(self, monkeypatch):
        monkeypatch.setattr(m.shutil, "which", lambda _: "/usr/bin/osascript")
        monkeypatch.setattr(m, "_tty_for_pid", lambda pid: None)
        r = m.inject_live(1234, "hello")
        assert r["ok"] is False
        assert "TTY" in r["error"] or "tty" in r["error"]

    def test_iterm2_match_returns_first(self, monkeypatch):
        captured = self._stub_environment(monkeypatch, tty="ttys123")
        r = m.inject_live(5154, "계속 시작.")
        assert r["ok"] is True
        assert r["mechanism"] == "iterm"
        assert r["tty"] == "/dev/ttys123"
        assert r["tried"] == ["iterm"]
        # Default press_choice="1" prepended.
        assert captured["iterm2_calls"][0]["keys"] == ["1", "계속 시작."]
        # Terminal.app is NOT called when iTerm2 succeeded.
        assert captured["terminal_calls"] == []

    def test_iterm2_miss_falls_back_to_terminal_app(self, monkeypatch):
        captured = self._stub_environment(
            monkeypatch, tty="ttys123",
            iterm_result=(False, "iterm2: no match"),
            term_result=(True, "terminal-app"),
        )
        r = m.inject_live(5154, "go")
        assert r["ok"] is True
        assert r["mechanism"] == "terminal-app"
        assert r["tried"] == ["iterm", "terminal-app"]
        # Both saw the keystroke list.
        assert captured["iterm2_calls"][0]["keys"] == ["1", "go"]
        assert captured["terminal_calls"][0]["keys"] == ["1", "go"]

    def test_both_miss_no_terminal_detected(self, monkeypatch):
        # AppleScript misses for both iTerm/Terminal AND no terminal
        # app detected in the process tree → final error.
        self._stub_environment(
            monkeypatch, tty="ttys999",
            iterm_result=(False, "iterm2: nada"),
            term_result=(False, "terminal-app: nada"),
            terminal_app=None,
        )
        r = m.inject_live(1234, "hello")
        assert r["ok"] is False
        assert r["mechanism"] is None
        # tried list won't include system-events because we skipped it.
        assert r["tried"] == ["iterm", "terminal-app"]
        assert "could not detect a terminal app" in r["error"]

    def test_press_choice_none_omits_choice_key(self, monkeypatch):
        captured = self._stub_environment(monkeypatch, tty="ttys001")
        m.inject_live(1234, "hello", press_choice=None)
        # Keys are just the prompt — no leading "1".
        assert captured["iterm2_calls"][0]["keys"] == ["hello"]

    def test_press_choice_custom(self, monkeypatch):
        captured = self._stub_environment(monkeypatch, tty="ttys001")
        m.inject_live(1234, "hello", press_choice="2")
        assert captured["iterm2_calls"][0]["keys"] == ["2", "hello"]

    def test_falls_back_to_system_events_when_apple_script_misses(self, monkeypatch):
        # Process tree shows Warp — smart routing skips iTerm /
        # Terminal AppleScript probes (they'd hang) and goes
        # straight to System Events.
        captured = self._stub_environment(
            monkeypatch, tty="ttys000",
            iterm_result=(False, "iterm: no match"),
            term_result=(False, "terminal-app: no match"),
            terminal_app="Warp",
        )
        r = m.inject_live(5154, "계속 시작.")
        assert r["ok"] is True
        assert r["mechanism"] == "system-events:Warp"
        assert r["terminalApp"] == "Warp"
        # Smart routing: only system-events tried.
        assert r["tried"] == ["system-events:Warp"]
        assert captured["se_calls"][0]["app"] == "Warp"
        assert captured["se_calls"][0]["keys"] == ["1", "계속 시작."]
        # iTerm/Terminal NOT called because process tree said Warp.
        assert captured["iterm2_calls"] == []
        assert captured["terminal_calls"] == []

    def test_unknown_terminal_still_tries_apple_script_strategies(self, monkeypatch):
        # When _detect_terminal_app returns None, we still try iTerm
        # and Terminal.app AppleScript paths (no info to short-circuit).
        captured = self._stub_environment(
            monkeypatch, tty="ttys000",
            iterm_result=(True, "iterm"),
            terminal_app=None,
        )
        r = m.inject_live(5154, "go")
        assert r["ok"] is True
        assert r["mechanism"] == "iterm"
        assert "iterm" in r["tried"]

    def test_system_events_disabled_returns_error(self, monkeypatch):
        captured = self._stub_environment(
            monkeypatch, tty="ttys000",
            iterm_result=(False, "no match"),
            term_result=(False, "no match"),
            terminal_app="Warp",
        )
        r = m.inject_live(5154, "go", allow_system_events=False)
        assert r["ok"] is False
        assert "System Events fallback disabled" in r["error"]
        assert captured["se_calls"] == []

    def test_no_terminal_detected_after_apple_script_miss(self, monkeypatch):
        captured = self._stub_environment(
            monkeypatch, tty="ttys000",
            iterm_result=(False, "no match"),
            term_result=(False, "no match"),
            terminal_app=None,
        )
        r = m.inject_live(5154, "go")
        assert r["ok"] is False
        assert "could not detect a terminal app" in r["error"]
        assert captured["se_calls"] == []  # never tried

    def test_system_events_failure_surfaces_error(self, monkeypatch):
        self._stub_environment(
            monkeypatch, tty="ttys000",
            iterm_result=(False, "no match"),
            term_result=(False, "no match"),
            se_result=(False, "system-events:error -1719 Cannot find process"),
            terminal_app="Warp",
        )
        r = m.inject_live(5154, "go")
        assert r["ok"] is False
        assert "all strategies failed" in r["error"]
        assert "Warp" in r["error"]


# ───────── _detect_terminal_app ─────────

class TestDetectTerminalApp:
    def test_finds_warp_in_chain(self, monkeypatch):
        # Mimic ps output: pid 5154 (claude) → 4219 (zsh) → 1056 (warp stable) → 945 (warp main)
        chain = {
            5154: ("claude --dangerously-skip-permissions", 4219),
            4219: ("-zsh -g --no_rcs", 1056),
            1056: ("/Applications/Warp.app/Contents/MacOS/stable terminal-server", 945),
            945: ("/Applications/Warp.app/Contents/MacOS/stable", 1),
        }
        monkeypatch.setattr(m, "_command_of", lambda pid: chain.get(pid, ("", 0))[0])
        monkeypatch.setattr(m, "_ppid_of", lambda pid: chain.get(pid, ("", 0))[1])
        assert m._detect_terminal_app(5154) == "Warp"

    def test_finds_iterm_in_chain(self, monkeypatch):
        chain = {
            100: ("claude", 99),
            99: ("-zsh", 50),
            50: ("/Applications/iTerm.app/Contents/MacOS/iTerm2", 1),
        }
        monkeypatch.setattr(m, "_command_of", lambda pid: chain.get(pid, ("", 0))[0])
        monkeypatch.setattr(m, "_ppid_of", lambda pid: chain.get(pid, ("", 0))[1])
        assert m._detect_terminal_app(100) == "iTerm2"

    def test_returns_none_for_unknown_terminal(self, monkeypatch):
        chain = {
            100: ("claude", 99),
            99: ("-zsh", 50),
            50: ("launchd", 1),  # not a terminal
        }
        monkeypatch.setattr(m, "_command_of", lambda pid: chain.get(pid, ("", 0))[0])
        monkeypatch.setattr(m, "_ppid_of", lambda pid: chain.get(pid, ("", 0))[1])
        assert m._detect_terminal_app(100) is None

    def test_breaks_on_root_pid(self, monkeypatch):
        # Walk should stop at pid <= 1 without infinite-looping.
        monkeypatch.setattr(m, "_command_of", lambda pid: "")
        monkeypatch.setattr(m, "_ppid_of", lambda pid: 1 if pid != 1 else None)
        assert m._detect_terminal_app(100) is None

    def test_handles_circular_parent(self, monkeypatch):
        # Buggy `ps` output where pid → ppid → pid → ... — the
        # `seen` set must short-circuit so we don't loop forever.
        monkeypatch.setattr(m, "_command_of", lambda pid: "noise")
        monkeypatch.setattr(m, "_ppid_of", lambda pid: 100 if pid == 50 else 50)
        assert m._detect_terminal_app(100) is None  # no terminal match


# ───────── _system_events_inject ─────────

class TestSystemEventsInject:
    def test_empty_keystrokes_returns_error(self):
        ok, err = m._system_events_inject("Warp", [])
        assert ok is False
        assert "no keystrokes" in err

    def test_invokes_target_app_via_activate(self, monkeypatch):
        called = {}

        def fake_run(script, **kw):
            called["script"] = script
            return True, "system-events:ok"

        monkeypatch.setattr(m, "_run_osascript", fake_run)
        ok, msg = m._system_events_inject("Warp", ["1", "go"])
        assert ok is True
        assert msg == "system-events:Warp"
        # Script must `activate` the app and target System Events.
        assert "tell application appName to activate" in called["script"]
        assert "tell application \"System Events\"" in called["script"]
        # Both keystrokes appear via clipboard-paste.
        assert '"1"' in called["script"]
        assert '"go"' in called["script"]
        # Cmd+V keystroke present.
        assert 'keystroke "v" using command down' in called["script"]
        # Return key code 36.
        assert "key code 36" in called["script"]

    def test_osascript_error_propagates(self, monkeypatch):
        monkeypatch.setattr(m, "_run_osascript", lambda *a, **kw: (False, "permission denied"))
        ok, err = m._system_events_inject("Warp", ["go"])
        assert ok is False
        assert "permission denied" in err

    def test_unicode_prompt_handled(self, monkeypatch):
        called = {}
        monkeypatch.setattr(m, "_run_osascript", lambda script, **kw: (called.update({"s": script}), (True, "system-events:ok"))[1])
        ok, _ = m._system_events_inject("Warp", ["1", "계속 시작."])
        assert ok is True
        # Korean string is passed through to clipboard literal.
        assert "계속 시작." in called["s"]


# ───────── _iterm2_inject AppleScript composition ─────────

class TestITermAppleScriptComposition:
    def test_script_includes_target_tty(self, monkeypatch):
        called = {}

        def fake_run(script, **kw):
            called["script"] = script
            return True, "iterm2:matched"

        monkeypatch.setattr(m, "_run_osascript", fake_run)
        ok, _ = m._iterm2_inject("ttys123", ["1", "hello"])
        assert ok is True
        # The script must contain the full TTY path so AppleScript
        # can string-compare against `tty of s`.
        assert "/dev/ttys123" in called["script"]
        # Both keystrokes appear.
        assert '"1"' in called["script"]
        assert '"hello"' in called["script"]

    def test_no_match_returns_false(self, monkeypatch):
        monkeypatch.setattr(m, "_run_osascript", lambda *a, **kw: (True, "iterm2:no-match"))
        ok, msg = m._iterm2_inject("ttys123", ["x"])
        assert ok is False
        assert "no session" in msg

    def test_special_chars_escaped(self, monkeypatch):
        called = {}

        def fake_run(script, **kw):
            called["script"] = script
            return True, "iterm2:matched"

        monkeypatch.setattr(m, "_run_osascript", fake_run)
        # The prompt has a quote; the embedded literal must be escaped.
        m._iterm2_inject("ttys001", ['say "hi"'])
        # Final script must NOT contain a raw unescaped pair that
        # would unbalance the AppleScript string.
        assert '\\"hi\\"' in called["script"]


# ───────── api_auto_resume_inject_live (integration) ─────────

class TestApiInjectLive:
    def test_missing_session_id(self):
        from server.auto_resume import api_auto_resume_inject_live
        r = api_auto_resume_inject_live({"prompt": "go"})
        assert r["ok"] is False
        assert "sessionId" in r["error"]

    def test_missing_prompt(self):
        from server.auto_resume import api_auto_resume_inject_live
        r = api_auto_resume_inject_live({"sessionId": "s1"})
        assert r["ok"] is False
        assert "prompt" in r["error"]

    def test_press_choice_skip_normalises_to_none(self, monkeypatch, tmp_path):
        from server import auto_resume as ar
        from server.auto_resume import api_auto_resume_inject_live

        captured = {}

        def fake_inject(pid, prompt, *, press_choice=None, allow_system_events=True):
            captured["pid"] = pid
            captured["prompt"] = prompt
            captured["press_choice"] = press_choice
            return {"ok": True, "mechanism": "test", "tty": "/dev/ttys999", "tried": ["test"], "error": None}

        # Stub the live session map to provide a PID.
        monkeypatch.setattr(ar, "_live_cli_sessions", lambda: {"s1": {"pid": 5154}})
        # Patch the imported function inside the module that uses it.
        import server.auto_resume_inject
        monkeypatch.setattr(server.auto_resume_inject, "inject_live", fake_inject)

        # Each null-ish value resolves to None.
        for skip_val in [None, "", "skip"]:
            r = api_auto_resume_inject_live({"sessionId": "s1", "prompt": "go", "pressChoice": skip_val})
            assert r["ok"] is True, (skip_val, r)
            assert captured["press_choice"] is None, skip_val

    def test_press_choice_default_is_one(self, monkeypatch):
        from server import auto_resume as ar
        from server.auto_resume import api_auto_resume_inject_live
        captured = {}
        def fake_inject(pid, prompt, *, press_choice=None, allow_system_events=True):
            captured["press_choice"] = press_choice
            return {"ok": True, "mechanism": "test", "tty": "/dev/ttys999", "tried": ["test"], "error": None}
        monkeypatch.setattr(ar, "_live_cli_sessions", lambda: {"s1": {"pid": 5154}})
        import server.auto_resume_inject
        monkeypatch.setattr(server.auto_resume_inject, "inject_live", fake_inject)
        api_auto_resume_inject_live({"sessionId": "s1", "prompt": "go"})
        assert captured["press_choice"] == "1"

    def test_no_live_pid_returns_error(self, monkeypatch):
        from server import auto_resume as ar
        from server.auto_resume import api_auto_resume_inject_live
        # Empty live map AND empty store → no PID.
        monkeypatch.setattr(ar, "_live_cli_sessions", lambda: {})
        monkeypatch.setattr(ar, "_load_all", lambda: {})
        r = api_auto_resume_inject_live({"sessionId": "ghost", "prompt": "go"})
        assert r["ok"] is False
        assert "no live PID" in r["error"]
