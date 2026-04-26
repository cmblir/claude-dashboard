"""Obsidian log appender — drops markdown into a vault under
`<vault>/Projects/<project>/logs/YYYY-MM-DD.md`.

Used by the `obsidian_log` workflow node and the Crew Wizard. Lightweight: no
HTTP, no MCP, just file append. The vault path must resolve under the user's
home directory (defense-in-depth against path traversal).
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logger import log
from .utils import _safe_read

_PROJECT_RE = re.compile(r"^[A-Za-z0-9 _\-./]{1,80}$")


def _under_home(raw: str) -> Optional[str]:
    """Resolve `raw` to an absolute path under $HOME, else None."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        expanded = os.path.expanduser(raw.strip())
        abs_p = os.path.abspath(expanded)
        real_p = os.path.realpath(abs_p)
    except Exception:
        return None
    home = os.path.realpath(str(Path.home()))
    if real_p == home or real_p.startswith(home + os.sep):
        return real_p
    return None


def append_log(vault_path: str, project: str, content: str,
               heading: str = "", tags: Optional[list] = None) -> dict:
    """Append a markdown entry to today's log file.

    Returns: {ok, path, bytesWritten, created} or {ok:False, error}.
    """
    safe_vault = _under_home(vault_path)
    if not safe_vault:
        return {"ok": False, "error": "vault path must resolve under $HOME"}
    if not project or not _PROJECT_RE.match(project):
        return {"ok": False, "error": "invalid project name"}
    if not isinstance(content, str):
        content = str(content)
    content = content[:64_000]  # 64 KB hard cap per entry

    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = Path(safe_vault) / "Projects" / project / "logs"
    log_path = log_dir / f"{today}.md"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": f"mkdir failed: {e}"}

    now = datetime.now().strftime("%H:%M:%S")
    parts = [f"\n## {now}" + (f" — {heading}" if heading else "")]
    if tags:
        clean = [t.strip().lstrip("#") for t in tags if isinstance(t, str)][:8]
        clean = [t for t in clean if re.match(r"^[A-Za-z0-9_\-]{1,40}$", t)]
        if clean:
            parts.append(" ".join(f"#{t}" for t in clean))
    parts.append(content)
    parts.append("")  # trailing blank line for next entry

    block = "\n".join(parts)

    created = not log_path.exists()
    if created:
        header = f"# {project} — {today}\n\n"
        try:
            log_path.write_text(header + block, encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"write failed: {e}"}
    else:
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(block)
        except Exception as e:
            return {"ok": False, "error": f"append failed: {e}"}

    try:
        size = log_path.stat().st_size
    except Exception:
        size = 0
    return {
        "ok": True,
        "path": str(log_path),
        "bytesWritten": len(block.encode("utf-8")),
        "totalBytes": size,
        "created": created,
        "ts": int(time.time() * 1000),
    }


# ───────── HTTP endpoint ─────────

def api_obsidian_test(body: dict) -> dict:
    """POST /api/obsidian/test — try writing a probe entry. Used by wizard UI."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    vault = (body.get("vaultPath") or "").strip()
    project = (body.get("project") or "lazyclaude-test").strip()
    return append_log(
        vault,
        project,
        "_LazyClaude wizard connectivity probe — safe to delete._",
        heading="probe",
        tags=["test"],
    )
