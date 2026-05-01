"""Project Ralph recommender.

Given a project (anywhere on disk that has a ``CLAUDE.md`` or git history),
synthesize a PROMPT.md draft suitable for feeding to ``server.ralph``.

Inputs (all best-effort, missing pieces are silently skipped):

- ``CLAUDE.md`` at the project root or under ``.claude/`` — the canonical
  intent of the project.
- ``git log --oneline -n 30`` — what's been happening recently.
- ``git status --porcelain`` — current work-in-progress.
- TODO / FIXME grep across tracked source files (capped).
- The most recent unfinished workflow run referencing that cwd, if any.

Output: a structured PROMPT.md draft (Markdown) and a short rationale, both
returned as plain text. The draft includes:

  - Goal preamble (from CLAUDE.md tagline if available, otherwise generic).
  - Top N candidate tasks, each with file/line context.
  - Hard rules (don't break tests, run ``make i18n-verify`` if applicable, ...).
  - The required completion-promise marker.

The recommender does not call an LLM. The synthesis is mechanical so the
function is fast, deterministic, and free. Callers can pipe the output into
``execute_with_assignee`` for an LLM-polished version if they want — that's
left to the UI layer.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b[:\s-]*(.{0,160})", re.IGNORECASE)
_TAGLINE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_GIT_TIMEOUT = 5
_MAX_TODO = 30
_MAX_GIT_LINES = 30


@dataclass
class Recommendation:
    project: str
    promptMd: str
    rationale: str
    completion: str = "<promise>DONE</promise>"
    sources: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "project":    self.project,
            "promptMd":   self.promptMd,
            "rationale":  self.rationale,
            "completion": self.completion,
            "sources":    self.sources,
        }


# ───────── Source extraction ─────────

def _read_claude_md(root: Path) -> str:
    for cand in (root / "CLAUDE.md",
                 root / ".claude" / "CLAUDE.md",
                 root / "claude.md"):
        if cand.is_file():
            try:
                return cand.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return ""


def _git(cmd: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(
            cmd, cwd=str(cwd), check=False, capture_output=True,
            text=True, timeout=_GIT_TIMEOUT,
        )
        return out.stdout if out.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _git_log(root: Path) -> list[str]:
    raw = _git(["git", "log", "--oneline", f"-n{_MAX_GIT_LINES}"], root)
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def _git_status(root: Path) -> list[str]:
    raw = _git(["git", "status", "--porcelain"], root)
    return [ln for ln in raw.splitlines() if ln.strip()]


def _grep_todos(root: Path, max_items: int = _MAX_TODO) -> list[tuple[str, int, str]]:
    """Return ``[(path, line, snippet)]``. Uses ``git grep`` when the project
    is a git repo (fast, respects .gitignore); falls back to a bounded
    Python walk over text files otherwise.
    """
    items: list[tuple[str, int, str]] = []
    git_grep = _git(
        ["git", "grep", "-nIE", "TODO|FIXME|XXX|HACK", "--",
         "*.py", "*.ts", "*.tsx", "*.js", "*.go", "*.rs", "*.java", "*.md"],
        root,
    )
    if git_grep:
        for ln in git_grep.splitlines():
            m = re.match(r"^([^:]+):(\d+):(.*)$", ln)
            if not m:
                continue
            path = m.group(1); line = int(m.group(2))
            snippet = m.group(3).strip()[:160]
            items.append((path, line, snippet))
            if len(items) >= max_items:
                return items
        return items

    # Non-git fallback — walk a small set of text extensions.
    exts = {".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".md"}
    for p in root.rglob("*"):
        if len(items) >= max_items:
            break
        if not p.is_file() or p.suffix not in exts:
            continue
        # skip vendor / build dirs
        parts = p.parts
        if any(seg in {"node_modules", "dist", "build", ".venv", "venv",
                       "__pycache__", ".git"} for seg in parts):
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8",
                                                  errors="ignore").splitlines(),
                                      start=1):
                m = _TODO_RE.search(line)
                if m:
                    items.append((str(p.relative_to(root)), i,
                                  line.strip()[:160]))
                    if len(items) >= max_items:
                        break
        except Exception:
            continue
    return items


def _project_root(path: str) -> Path:
    """Resolve to a sensible project root. We deliberately do NOT walk past
    the user's HOME — preserves the same invariant ``server/utils.py``
    enforces with ``_under_home``.
    """
    p = Path(os.path.expanduser(path)).resolve()
    return p


# ───────── Synthesis ─────────

def _extract_tagline(claude_md: str) -> str:
    m = _TAGLINE_RE.search(claude_md or "")
    if not m:
        return ""
    line = m.group(1).strip()
    # Strip leading emoji + project-name prefixes — keep the part after a dash
    # if it's "name — purpose".
    if " — " in line:
        return line.split(" — ", 1)[1].strip()
    return line


def recommend(project_path: str) -> Optional[Recommendation]:
    root = _project_root(project_path)
    if not root.is_dir():
        return None

    claude_md = _read_claude_md(root)
    log_lines  = _git_log(root)
    dirty      = _git_status(root)
    todos      = _grep_todos(root)
    tagline    = _extract_tagline(claude_md)

    # Top-level "what to do" reasoning is mechanical:
    # 1. If there are uncommitted changes, finishing them is the highest
    #    leverage move.
    # 2. Else if there are TODOs, work the top 5 by priority order
    #    (TODO > FIXME > XXX > HACK).
    # 3. Else propose a "next iteration" loop based on tagline.
    sections: list[str] = []
    rationale_parts: list[str] = []

    if tagline:
        sections.append(f"## Project context\n{tagline}\n")
    elif claude_md:
        # First non-empty paragraph as fallback.
        first = next((p.strip() for p in claude_md.split("\n\n")
                      if p.strip() and not p.lstrip().startswith("#")), "")
        if first:
            sections.append(f"## Project context\n{first[:500]}\n")

    if dirty:
        rationale_parts.append(f"{len(dirty)} uncommitted file(s) — finishing "
                               "in-progress work first.")
        bullets = "\n".join(f"- {ln}" for ln in dirty[:15])
        sections.append("## Goal A — finish work in progress\n"
                        f"The repo has uncommitted changes. Drive these to a "
                        f"clean state (passing tests, no dirty tree):\n\n"
                        f"```\n{bullets}\n```\n")

    if todos:
        priority_order = {"TODO": 0, "FIXME": 1, "XXX": 2, "HACK": 3}
        def _key(t):
            kind = "TODO"
            for k in priority_order:
                if k.lower() in t[2].lower():
                    kind = k; break
            return priority_order.get(kind, 9)
        ranked = sorted(todos, key=_key)[:5]
        rationale_parts.append(f"{len(todos)} TODO/FIXME found (top 5 surfaced).")
        bullets = "\n".join(
            f"- `{p}:{ln}` — {snippet}" for p, ln, snippet in ranked
        )
        sections.append("## Goal B — clear top TODOs\n"
                        "Pick these in order, smallest blast radius first:\n\n"
                        f"{bullets}\n")

    if log_lines:
        rationale_parts.append(
            f"recent log: {len(log_lines)} commits scanned, latest is "
            f"`{log_lines[0][:60]}…`"
        )
        sections.append("## Recent context (last commits)\n```\n"
                        + "\n".join(log_lines[:10]) + "\n```\n")

    if not sections:
        sections.append("## Goal\nNo CLAUDE.md, no TODOs, no git history. "
                        "Inspect the project and propose three concrete "
                        "improvements, then implement them.\n")
        rationale_parts.append("empty signal — generic exploratory loop.")

    sections.append(
        "## Rules\n"
        "- Do not break existing passing tests. Run them after every change.\n"
        "- Keep diffs minimal — one logical change per commit.\n"
        "- If you encounter a blocker that's larger than 30 minutes of work, "
        "document it in `BLOCKERS.md` and move to the next item.\n"
        "- When the goals above are satisfied **and** tests pass and the "
        "tree is clean, output exactly:\n\n"
        "  `<promise>DONE</promise>`\n"
    )

    prompt_md = f"# Ralph: {root.name}\n\n" + "\n".join(sections)
    rationale = " · ".join(rationale_parts)

    return Recommendation(
        project=str(root),
        promptMd=prompt_md,
        rationale=rationale,
        completion="<promise>DONE</promise>",
        sources={
            "hasClaudeMd": bool(claude_md),
            "gitLogLines": len(log_lines),
            "dirtyFiles":  len(dirty),
            "todoCount":   len(todos),
        },
    )


# ───────── HTTP API ─────────

def api_ralph_recommend(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    project = (body.get("project") or "").strip()
    if not project:
        return {"ok": False, "error": "project path required"}
    rec = recommend(project)
    if rec is None:
        return {"ok": False, "error": "project not found"}
    return {"ok": True, "recommendation": rec.to_dict()}
