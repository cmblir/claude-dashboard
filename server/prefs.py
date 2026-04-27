"""User preferences — centralised key/value store for the Quick Settings panel.

Persists per-user dashboard preferences (UI, AI defaults, behaviour,
workflow defaults) in ``~/.claude-dashboard-prefs.json``. The frontend uses
``GET /api/prefs/get`` on boot, then ``POST /api/prefs/set`` for incremental
updates as the user toggles controls.

Design rules:
- All values are strictly validated against ``PREFS_SCHEMA`` before write —
  silent-drop unknown keys, coerce types, clamp numbers, enum-check strings.
- Writes go through ``_safe_write`` (atomic tmp + rename).
- Defaults live in ``DEFAULT_PREFS`` and are merged on read so old files keep
  working when new keys are added.
"""
from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write


PREFS_PATH = _env_path(
    "CLAUDE_DASHBOARD_PREFS",
    Path.home() / ".claude-dashboard-prefs.json",
)


# ───────── Schema ─────────
# Tuple form: (kind, constraint)
#   kind=enum  → constraint = list[str]
#   kind=bool  → constraint = None
#   kind=int   → constraint = (lo, hi) inclusive
#   kind=float → constraint = (lo, hi) inclusive
#   kind=str   → constraint = max length

PREFS_SCHEMA: dict[str, dict[str, tuple]] = {
    "ui": {
        "theme":            ("enum", ["auto", "dark", "light", "midnight", "forest", "sunset"]),
        "lang":             ("enum", ["ko", "en", "zh"]),
        "density":          ("enum", ["compact", "comfortable", "spacious"]),
        "fontSize":         ("enum", ["small", "medium", "large", "xlarge"]),
        "reducedMotion":    ("bool", None),
        "accentColor":      ("enum", ["claude", "blue", "purple", "green", "orange", "pink"]),
        "sidebarCollapsed": ("bool", None),
        "mascotEnabled":    ("bool", None),
        "compactSidebar":   ("bool", None),
    },
    "ai": {
        "defaultProvider":  ("str", 120),
        "effort":           ("enum", ["minimal", "low", "medium", "high"]),
        "temperature":      ("float", (0.0, 2.0)),
        "topP":             ("float", (0.0, 1.0)),
        "maxOutputTokens":  ("int", (1, 200000)),
        "thinkingBudget":   ("int", (0, 200000)),
        "extendedThinking": ("bool", None),
        "streamResponses":  ("bool", None),
        "fallbackChain":    ("bool", None),
    },
    "behavior": {
        "autoResume":        ("bool", None),
        "notifySlack":       ("bool", None),
        "notifyDiscord":     ("bool", None),
        "telemetryRefresh":  ("int", (0, 3600)),
        "confirmSpawn":      ("bool", None),
        "autosaveWorkflows": ("bool", None),
        "liveTickerSeconds": ("int", (1, 600)),
        "soundOnComplete":   ("bool", None),
        "openLastTab":       ("bool", None),
    },
    "workflow": {
        "defaultIterations":     ("int", (1, 50)),
        "defaultRepeatDelaySec": ("int", (0, 3600)),
        "dryRunByDefault":       ("bool", None),
        "showMinimap":           ("bool", None),
        "snapToGrid":            ("bool", None),
        "gridSize":              ("int", (8, 64)),
    },
}

DEFAULT_PREFS: dict[str, dict[str, Any]] = {
    "ui": {
        "theme":            "auto",
        "lang":             "ko",
        "density":          "comfortable",
        "fontSize":         "medium",
        "reducedMotion":    False,
        "accentColor":      "claude",
        "sidebarCollapsed": False,
        "mascotEnabled":    True,
        "compactSidebar":   False,
    },
    "ai": {
        "defaultProvider":  "claude:sonnet",
        "effort":           "medium",
        "temperature":      0.7,
        "topP":             1.0,
        "maxOutputTokens":  4096,
        "thinkingBudget":   0,
        "extendedThinking": False,
        "streamResponses":  True,
        "fallbackChain":    True,
    },
    "behavior": {
        "autoResume":        True,
        "notifySlack":       False,
        "notifyDiscord":     False,
        "telemetryRefresh":  30,
        "confirmSpawn":      False,
        "autosaveWorkflows": True,
        "liveTickerSeconds": 5,
        "soundOnComplete":   False,
        "openLastTab":       True,
    },
    "workflow": {
        "defaultIterations":     1,
        "defaultRepeatDelaySec": 0,
        "dryRunByDefault":       False,
        "showMinimap":           True,
        "snapToGrid":            False,
        "gridSize":              16,
    },
}


# ───────── Validation ─────────

def _coerce(kind: str, constraint: Any, raw: Any, default: Any) -> Any:
    """Validate and coerce a single value against its schema entry.

    Returns ``default`` whenever the input cannot be safely coerced — this is
    deliberate so the API never raises on malformed payloads, it just ignores
    them.
    """
    try:
        if kind == "bool":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, (int, float)):
                return bool(raw)
            if isinstance(raw, str):
                return raw.lower() in ("1", "true", "yes", "on")
            return default
        if kind == "enum":
            s = str(raw).strip()
            return s if s in constraint else default
        if kind == "int":
            v = int(float(raw))
            lo, hi = constraint
            if v < lo:
                v = lo
            if v > hi:
                v = hi
            return v
        if kind == "float":
            v = float(raw)
            lo, hi = constraint
            if v < lo:
                v = lo
            if v > hi:
                v = hi
            return round(v, 4)
        if kind == "str":
            s = str(raw)
            if len(s) > constraint:
                s = s[:constraint]
            return s
    except Exception:
        return default
    return default


def _validate_section(section: str, payload: dict, base: dict) -> dict:
    """Merge ``payload`` keys into ``base`` for a given section, validating each."""
    schema = PREFS_SCHEMA.get(section) or {}
    out = dict(base)
    for k, v in (payload or {}).items():
        if k not in schema:
            continue  # silent-drop unknown
        kind, cons = schema[k]
        out[k] = _coerce(kind, cons, v, base.get(k, DEFAULT_PREFS[section][k]))
    return out


def _merged_with_defaults(stored: dict) -> dict:
    """Ensure every section/key from defaults exists, validating stored values."""
    out: dict = {}
    for section, defaults in DEFAULT_PREFS.items():
        stored_section = (stored or {}).get(section) or {}
        out[section] = _validate_section(section, stored_section, deepcopy(defaults))
    return out


# ───────── Persistence ─────────

def _read_file() -> dict:
    if not PREFS_PATH.exists():
        return {}
    raw = _safe_read(PREFS_PATH)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("prefs load failed: %s", e)
        return {}


def load_prefs() -> dict:
    """Return prefs merged with defaults — safe even if the file is missing or
    partially corrupt."""
    return _merged_with_defaults(_read_file())


def _write(prefs: dict) -> bool:
    text = json.dumps(prefs, ensure_ascii=False, indent=2, sort_keys=True)
    return _safe_write(PREFS_PATH, text)


# ───────── HTTP handlers ─────────

def api_prefs_get(query: dict) -> dict:
    """GET /api/prefs/get → ``{ prefs, defaults, schema, savedAt }``."""
    prefs = load_prefs()
    return {
        "ok":       True,
        "prefs":    prefs,
        "defaults": DEFAULT_PREFS,
        "schema":   _serialise_schema(),
        "savedAt":  _stat_mtime(),
    }


def api_prefs_set(body: dict) -> dict:
    """POST /api/prefs/set — body shape::

        { "section": "ui", "key": "theme", "value": "midnight" }

    or batch::

        { "patch": { "ui": {"theme": "midnight"}, "ai": {"effort": "high"} } }
    """
    body = body or {}
    current = load_prefs()

    if "patch" in body and isinstance(body["patch"], dict):
        patch = body["patch"]
    elif "section" in body and "key" in body:
        patch = {body["section"]: {body["key"]: body.get("value")}}
    else:
        return {"ok": False, "error": "missing 'patch' or 'section'+'key'"}

    next_prefs: dict = {}
    for section, defaults in DEFAULT_PREFS.items():
        section_patch = patch.get(section) if isinstance(patch.get(section), dict) else {}
        base = dict(current.get(section) or defaults)
        next_prefs[section] = _validate_section(section, section_patch or {}, base)

    ok = _write(next_prefs)
    return {"ok": bool(ok), "prefs": next_prefs, "savedAt": _stat_mtime() if ok else 0}


def api_prefs_reset(body: dict) -> dict:
    """POST /api/prefs/reset — wipe the whole file or a single section.

    Body::
        {}                       → reset everything
        { "section": "ui" }      → reset UI section only
    """
    body = body or {}
    section = (body.get("section") or "").strip()
    if section and section in DEFAULT_PREFS:
        current = load_prefs()
        current[section] = deepcopy(DEFAULT_PREFS[section])
        ok = _write(current)
        return {"ok": bool(ok), "prefs": current}
    ok = _write(deepcopy(DEFAULT_PREFS))
    return {"ok": bool(ok), "prefs": deepcopy(DEFAULT_PREFS)}


# ───────── Helpers ─────────

def _serialise_schema() -> dict:
    """Return schema in a JSON-friendly shape so the frontend can render
    controls without hard-coding the constraints again."""
    out: dict = {}
    for section, fields in PREFS_SCHEMA.items():
        out[section] = {}
        for key, (kind, cons) in fields.items():
            entry: dict = {"kind": kind}
            if kind == "enum":
                entry["choices"] = list(cons)
            elif kind in ("int", "float"):
                entry["min"], entry["max"] = cons
            elif kind == "str":
                entry["maxLen"] = cons
            out[section][key] = entry
    return out


def _stat_mtime() -> int:
    try:
        return int(PREFS_PATH.stat().st_mtime * 1000)
    except Exception:
        return int(time.time() * 1000)


def get_pref(section: str, key: str, fallback: Any = None) -> Any:
    """Read a single pref — convenience for other server modules. Falls back to
    ``DEFAULT_PREFS`` then to the supplied ``fallback``."""
    try:
        return load_prefs().get(section, {}).get(key, DEFAULT_PREFS.get(section, {}).get(key, fallback))
    except Exception:
        return fallback
