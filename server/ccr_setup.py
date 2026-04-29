"""v2.45.0 — Claude Code Router (CCR / zclaude) setup wizard.

Read-only inspection + safe config edit + service control for the
`@musistudio/claude-code-router` (`ccr`) package. The dashboard tab
guides the user through:

  1. Status check         (node / ccr / claude / config / port 3456)
  2. Provider config edit (Providers[] + presets)
  3. Router rules         (default / background / think / longContext / webSearch)
  4. Service start/stop
  5. Shell alias snippet  (zclaude='ccr code')

Stdlib only. Never runs npm install autonomously — exposes the install
command string for the user to run themselves. Service control
(`ccr start|stop|restart`) is allowed because it is the user's own
local service on a fixed port.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

from .logger import log
from .utils import _safe_read, _safe_write


# ───────── constants ─────────

CCR_CONFIG_DIR = Path.home() / ".claude-code-router"
CCR_CONFIG_PATH = CCR_CONFIG_DIR / "config.json"
DEFAULT_PORT = 3456
DEFAULT_HOST = "127.0.0.1"

_NODE_MIN_MAJOR = 20
_CMD_TIMEOUT = 5
_SERVICE_TIMEOUT = 15

_ALLOWED_TOP_KEYS = {
    "APIKEY", "PROXY_URL", "LOG", "LOG_LEVEL", "HOST", "PORT",
    "NON_INTERACTIVE_MODE", "API_TIMEOUT_MS", "Providers", "Router",
}
_ALLOWED_LOG_LEVELS = {"fatal", "error", "warn", "info", "debug", "trace"}
_ALLOWED_ROUTER_KEYS = {
    "default", "background", "think", "longContext",
    "longContextThreshold", "webSearch", "image",
}

_ALIAS_BEGIN = "# >>> zclaude (lazyclaude) >>>"
_ALIAS_END = "# <<< zclaude (lazyclaude) <<<"
_ALIAS_BODY = (
    f"{_ALIAS_BEGIN}\n"
    "alias zclaude='ccr code'\n"
    '# alternatively: eval "$(ccr activate)" && claude\n'
    f"{_ALIAS_END}\n"
)


# ───────── helpers ─────────

def _run(cmd: list[str], timeout: int = _CMD_TIMEOUT) -> tuple[int, str, str]:
    """Run a command. Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # pragma: no cover
        return 1, "", str(e)


def _under_home(p: Path) -> bool:
    """Reject paths that resolve outside $HOME."""
    try:
        home = Path.home().resolve()
        return str(p.resolve()).startswith(str(home))
    except Exception:
        return False


def _expand_env(v: Any) -> Any:
    """Expand $VAR / ${VAR} in strings; recurse into dicts/lists."""
    if isinstance(v, str):
        return os.path.expandvars(v)
    if isinstance(v, dict):
        return {k: _expand_env(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand_env(x) for x in v]
    return v


def _port_listening(host: str, port: int) -> bool:
    """Cheap TCP probe — fast connect on 127.0.0.1."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def _service_pid(port: int) -> int:
    """Best-effort: PID of a process listening on `port` via lsof. 0 if unknown."""
    rc, out, _ = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], _CMD_TIMEOUT)
    if rc != 0 or not out:
        return 0
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                continue
    return 0


def _which(name: str) -> str:
    p = shutil.which(name)
    return p or ""


def _node_version() -> tuple[str, bool]:
    rc, out, _ = _run(["node", "--version"])
    if rc != 0 or not out:
        return "", False
    # `v20.11.0`
    m = re.match(r"^v?(\d+)\.", out)
    major = int(m.group(1)) if m else 0
    return out, major >= _NODE_MIN_MAJOR


def _tool_version(name: str) -> tuple[bool, str]:
    if not _which(name):
        return False, ""
    rc, out, _ = _run([name, "--version"])
    return (rc == 0, out if rc == 0 else "")


# ───────── config validation ─────────

def _coerce_provider(p: Any, warnings: list[str], idx: int) -> dict | None:
    if not isinstance(p, dict):
        warnings.append(f"Providers[{idx}]: not an object, dropped")
        return None
    name = str(p.get("name", "")).strip()
    api_base_url = str(p.get("api_base_url", "")).strip()
    api_key = str(p.get("api_key", "")) if p.get("api_key") is not None else ""
    models_raw = p.get("models", [])
    if not name or not api_base_url:
        warnings.append(f"Providers[{idx}]: missing name or api_base_url, dropped")
        return None
    if not isinstance(models_raw, list):
        warnings.append(f"Providers[{idx}]: models must be a list, dropped")
        return None
    models = [str(m).strip() for m in models_raw if str(m).strip()]
    out = dict(p)  # preserve unknown provider-level keys (transformer customizations etc.)
    out["name"] = name
    out["api_base_url"] = api_base_url
    out["api_key"] = api_key
    out["models"] = models
    return out


def _coerce_router(r: Any, warnings: list[str]) -> dict:
    if not isinstance(r, dict):
        if r is not None:
            warnings.append("Router: not an object, replaced with {}")
        return {}
    out: dict = {}
    for k, v in r.items():
        if k not in _ALLOWED_ROUTER_KEYS:
            warnings.append(f"Router: unknown key '{k}' dropped")
            continue
        if k == "longContextThreshold":
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                warnings.append("Router.longContextThreshold: not int, dropped")
        else:
            out[k] = str(v) if v is not None else ""
    return out


def _validate_config(cfg: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    if not isinstance(cfg, dict):
        return {}, ["top-level config must be an object"]
    out: dict = {}
    for k, v in cfg.items():
        if k not in _ALLOWED_TOP_KEYS:
            warnings.append(f"unknown top-level key '{k}' stripped")
            continue
        out[k] = v
    # type coerce / validate
    if "LOG" in out and not isinstance(out["LOG"], bool):
        out["LOG"] = bool(out["LOG"])
    if "NON_INTERACTIVE_MODE" in out and not isinstance(out["NON_INTERACTIVE_MODE"], bool):
        out["NON_INTERACTIVE_MODE"] = bool(out["NON_INTERACTIVE_MODE"])
    if "PORT" in out:
        try:
            out["PORT"] = int(out["PORT"])
        except (TypeError, ValueError):
            warnings.append("PORT: not int, removed")
            out.pop("PORT", None)
    if "API_TIMEOUT_MS" in out:
        try:
            out["API_TIMEOUT_MS"] = int(out["API_TIMEOUT_MS"])
        except (TypeError, ValueError):
            warnings.append("API_TIMEOUT_MS: not int, removed")
            out.pop("API_TIMEOUT_MS", None)
    if "LOG_LEVEL" in out:
        lvl = str(out["LOG_LEVEL"]).lower().strip()
        if lvl not in _ALLOWED_LOG_LEVELS:
            warnings.append(f"LOG_LEVEL: '{lvl}' invalid, removed")
            out.pop("LOG_LEVEL", None)
        else:
            out["LOG_LEVEL"] = lvl
    if "HOST" in out:
        out["HOST"] = str(out["HOST"]).strip() or DEFAULT_HOST
    # Providers
    raw_providers = out.get("Providers", [])
    if not isinstance(raw_providers, list):
        warnings.append("Providers: not a list, replaced with []")
        raw_providers = []
    providers: list[dict] = []
    for i, p in enumerate(raw_providers):
        coerced = _coerce_provider(p, warnings, i)
        if coerced is not None:
            providers.append(coerced)
    out["Providers"] = providers
    # Router
    out["Router"] = _coerce_router(out.get("Router"), warnings)
    return out, warnings


# ───────── path safety after env interpolation ─────────

def _config_path_safety(cfg: dict) -> str:
    """Return error message if config references local paths outside $HOME after $VAR expansion."""
    expanded = _expand_env(cfg)
    candidates: list[str] = []
    for prov in expanded.get("Providers") or []:
        if isinstance(prov, dict):
            url = str(prov.get("api_base_url", ""))
            if url.startswith("/") or url.startswith("file://"):
                candidates.append(url.replace("file://", ""))
    for c in candidates:
        try:
            p = Path(c)
            if not _under_home(p):
                return f"path '{c}' resolves outside $HOME"
        except Exception:
            continue
    return ""


# ───────── public API ─────────

def api_ccr_status(query: dict) -> dict:
    """GET /api/ccr/status — environment and service state."""
    node_ver, node_ok = _node_version()
    ccr_installed, ccr_ver = _tool_version("ccr")
    claude_installed, claude_ver = _tool_version("claude")
    cfg_exists = CCR_CONFIG_PATH.exists()
    # service port: prefer config if readable
    port = DEFAULT_PORT
    host = DEFAULT_HOST
    if cfg_exists:
        try:
            cfg = json.loads(_safe_read(CCR_CONFIG_PATH) or "{}")
            if isinstance(cfg.get("PORT"), int):
                port = cfg["PORT"]
            if isinstance(cfg.get("HOST"), str) and cfg["HOST"].strip():
                host = cfg["HOST"].strip()
        except Exception:
            pass
    running = _port_listening(host, port)
    pid = _service_pid(port) if running else 0
    return {
        "ok": True,
        "node_version": node_ver,
        "node_ok": node_ok,
        "ccr_installed": ccr_installed,
        "ccr_version": ccr_ver,
        "claude_installed": claude_installed,
        "claude_version": claude_ver,
        "config_exists": cfg_exists,
        "config_path": str(CCR_CONFIG_PATH),
        "service_running": running,
        "service_host": host,
        "service_port": port,
        "service_pid": pid,
    }


def api_ccr_config_load(query: dict) -> dict:
    """GET /api/ccr/config — read the file (or empty default)."""
    if not CCR_CONFIG_PATH.exists():
        return {
            "ok": True,
            "exists": False,
            "config": {"LOG": True, "HOST": DEFAULT_HOST, "PORT": DEFAULT_PORT,
                       "Providers": [], "Router": {}},
            "raw": "",
        }
    raw = _safe_read(CCR_CONFIG_PATH)
    try:
        cfg = json.loads(raw) if raw else {}
    except Exception as e:
        return {"ok": False, "error": f"config parse failed: {e}", "raw": raw, "config": {}}
    return {"ok": True, "exists": True, "config": cfg, "raw": raw}


def api_ccr_config_save(body: dict) -> dict:
    """POST /api/ccr/config — atomic write after validation."""
    body = body or {}
    cfg = body.get("config")
    if not isinstance(cfg, dict):
        return {"ok": False, "error": "missing or invalid 'config' object"}
    sanitized, warnings = _validate_config(cfg)
    err = _config_path_safety(sanitized)
    if err:
        return {"ok": False, "error": f"path safety: {err}"}
    if not _under_home(CCR_CONFIG_PATH):
        return {"ok": False, "error": "config path outside $HOME"}
    text = json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n"
    if not _safe_write(CCR_CONFIG_PATH, text):
        return {"ok": False, "error": "write failed"}
    try:
        os.chmod(CCR_CONFIG_PATH, 0o600)
    except Exception:
        pass
    return {
        "ok": True,
        "path": str(CCR_CONFIG_PATH),
        "bytesWritten": len(text.encode("utf-8")),
        "warnings": warnings,
        "config": sanitized,
    }


def api_ccr_install_command(query: dict) -> dict:
    """GET /api/ccr/install-command — return the npm command without running it."""
    return {
        "ok": True,
        "command": "npm install -g @musistudio/claude-code-router",
        "note": (
            "Run this command in your terminal. Requires Node.js 20+. "
            "After installation, run 'ccr --version' to verify, then return here."
        ),
    }


def api_ccr_service(body: dict) -> dict:
    """POST /api/ccr/service — start/stop/restart the local ccr service."""
    body = body or {}
    action = str(body.get("action", "")).strip().lower()
    if action not in {"start", "stop", "restart", "status"}:
        return {"ok": False, "error": "action must be start|stop|restart|status"}
    if not _which("ccr"):
        return {"ok": False, "error": "ccr not installed"}
    rc, out, err = _run(["ccr", action], _SERVICE_TIMEOUT)
    return {
        "ok": rc == 0,
        "action": action,
        "exit_code": rc,
        "stdout": out,
        "stderr": err,
        "output": (out + ("\n" + err if err else "")).strip(),
    }


def _detect_shell() -> tuple[str, Path]:
    sh = os.environ.get("SHELL", "")
    name = Path(sh).name if sh else ""
    home = Path.home()
    if name == "zsh" or (not name and (home / ".zshrc").exists()):
        return "zsh", home / ".zshrc"
    if name == "bash":
        return "bash", home / ".bashrc"
    if name:
        return name, home / f".{name}rc"
    return "zsh", home / ".zshrc"


def api_ccr_alias_snippet(query: dict) -> dict:
    """GET /api/ccr/alias-snippet — generate the alias text. Never writes."""
    shell, rc_path = _detect_shell()
    already_present = False
    if rc_path.exists() and _under_home(rc_path):
        already_present = _ALIAS_BEGIN in _safe_read(rc_path)
    return {
        "ok": True,
        "current_shell": shell,
        "rc_path": str(rc_path),
        "already_present": already_present,
        "zshrc_snippet": _ALIAS_BODY,
        "bashrc_snippet": _ALIAS_BODY,
        "alternate_command": 'eval "$(ccr activate)" && claude',
        "reload_hint": f"source {rc_path}",
    }


# ───────── presets (provider templates) ─────────

_PRESETS: list[dict] = [
    {
        "id": "zai",
        "label": "Z.AI / GLM (aihubmix)",
        "name": "aihubmix",
        "api_base_url": "https://aihubmix.com/v1/chat/completions",
        "api_key_placeholder": "sk-aihubmix-...",
        "models": ["Z/glm-4.5", "Z/glm-4.6", "claude-sonnet-4-5", "gpt-5"],
        "transformer": None,
        "models_help": (
            "aihubmix proxies many providers including Z.AI's GLM family. "
            "Use 'Z/glm-4.6' for the strongest GLM tier."
        ),
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "name": "deepseek",
        "api_base_url": "https://api.deepseek.com/chat/completions",
        "api_key_placeholder": "sk-...",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "transformer": {"use": ["deepseek"]},
        "models_help": "deepseek-chat for general; deepseek-reasoner for stronger reasoning.",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "name": "openrouter",
        "api_base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_placeholder": "sk-or-...",
        "models": [
            "google/gemini-2.5-pro-preview",
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3.7-sonnet:thinking",
        ],
        "transformer": {"use": ["openrouter"]},
        "models_help": "OpenRouter aggregates many models. Add only the ones you need.",
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "name": "ollama",
        "api_base_url": "http://localhost:11434/v1/chat/completions",
        "api_key_placeholder": "ollama",
        "models": ["qwen2.5-coder:latest", "llama3.1:latest"],
        "transformer": None,
        "models_help": "Use any model already pulled with `ollama pull <name>`.",
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "name": "gemini",
        "api_base_url": "https://generativelanguage.googleapis.com/v1beta/models/",
        "api_key_placeholder": "AIza...",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "transformer": {"use": ["gemini"]},
        "models_help": "Direct Google AI Studio Gemini API. The transformer maps OpenAI-compatible payloads.",
    },
]


def api_ccr_presets(query: dict) -> dict:
    """GET /api/ccr/presets — provider templates for one-click insert."""
    return {"ok": True, "presets": _PRESETS}


# ───────── module log ─────────

log.debug("ccr_setup module loaded; config=%s", CCR_CONFIG_PATH)
