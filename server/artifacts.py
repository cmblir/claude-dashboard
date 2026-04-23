"""Artifacts Viewer (v2.33.0) — 워크플로우 출력물을 안전하게 미리보기.

**4중 보안 (v2.21.0 설계 계승)**
1. Sandbox iframe: `sandbox=""` (모든 권한 차단 — 스크립트 실행/폼/쿠키/네트워크 전부 불가)
2. CSP meta tag 주입: `default-src 'none'; style-src 'unsafe-inline'; img-src data:`
3. postMessage whitelist (프런트 — iframe 에서 부모로 향하는 메시지 필터)
4. 정적 필터: `<script>`, `<iframe>`, `<object>`, `<embed>`, `<link>`, `on*=`, `javascript:` URL 제거

지원 포맷:
- Markdown (.md / ``` code 감지) → 안전한 HTML 변환
- HTML → 정적 필터 → CSP iframe 렌더
- SVG → 정적 필터 (외부 이미지 차단) → iframe 렌더
- JSON → pretty print + 색상 없이 `<pre>`
- Code/text → `<pre>` 이스케이프

API:
- `GET /api/artifacts/list` — 최근 run 중 output 이 있는 것들
- `GET /api/artifacts/render?runId=...` — sanitized HTML (srcdoc 용)
"""
from __future__ import annotations

import html
import json
import re
from typing import Any

from .logger import log
from .workflows import _load_all


# ───────── 포맷 감지 ─────────

def _detect_format(text: str) -> str:
    t = (text or "").lstrip()
    if not t:
        return "text"
    # JSON
    if t.startswith("{") or t.startswith("["):
        try:
            json.loads(t)
            return "json"
        except Exception:
            pass
    # SVG
    if re.match(r"<\?xml[^>]*>\s*<svg", t, re.I) or t.startswith("<svg"):
        return "svg"
    # HTML (doctype / html root / 풍부한 태그)
    if re.match(r"<!doctype\s+html", t, re.I) or re.match(r"<html[\s>]", t, re.I):
        return "html"
    if "<body" in t.lower() or "<head" in t.lower():
        return "html"
    # Mermaid (```mermaid 블록)
    if re.search(r"```mermaid\b", t):
        return "markdown"
    # Markdown — 헤더/리스트/코드블록 표시자
    md_signals = sum(1 for p in (r"^#{1,6}\s", r"^\*\s", r"^-\s", r"^\d+\.\s", r"```") if re.search(p, t, re.M))
    if md_signals >= 2 or t.startswith("#"):
        return "markdown"
    return "text"


# ───────── 정적 필터 ─────────

_DANGEROUS_TAGS = re.compile(
    r"<\s*(script|iframe|object|embed|link|meta|base|form|input|button|textarea)"
    r"[^>]*>.*?(?:<\s*/\s*\1\s*>|$)",
    re.I | re.S,
)
_SELF_CLOSING_DANGER = re.compile(
    r"<\s*(link|meta|base|input|img)\s[^>]*>",
    re.I,
)
_EVENT_ATTR = re.compile(r"""\s+on[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_JS_URL = re.compile(r"""(?:href|src|xlink:href|action)\s*=\s*("|')\s*javascript:[^"'>\s]*\1""", re.I)
_DATA_HTML = re.compile(r"""(?:href|src)\s*=\s*("|')\s*data:text/html[^"'>\s]*\1""", re.I)


def _sanitize_html(raw: str) -> str:
    """HTML/SVG 내 위험 요소 제거. img 는 허용 (img-src data: 로 CSP 제한)."""
    if not isinstance(raw, str):
        return ""
    out = raw
    # 위험 태그 + 내용 삭제 (script/iframe/object 등)
    # self-closing/빈 요소도 커버
    out = _DANGEROUS_TAGS.sub("", out)
    # link/meta/base/input/img 중 img 는 유지, 나머지는 제거
    def _strip_sc(m):
        tag = re.match(r"<\s*(\w+)", m.group(0), re.I).group(1).lower()
        if tag == "img":
            # img 만 남기고 on*= / javascript: 제거는 아래에서
            return m.group(0)
        return ""
    out = _SELF_CLOSING_DANGER.sub(_strip_sc, out)
    # 이벤트 핸들러 onload= 등 제거
    out = _EVENT_ATTR.sub("", out)
    # javascript: / data:text/html URL 제거
    out = _JS_URL.sub("", out)
    out = _DATA_HTML.sub("", out)
    return out


# ───────── 포맷 변환 ─────────

def _md_to_safe_html(text: str) -> str:
    """매우 단순한 Markdown → HTML (외부 라이브러리 없음)."""
    if not isinstance(text, str):
        return ""
    lines = text.split("\n")
    out = []
    in_code = False
    code_buf: list[str] = []
    code_lang = ""
    in_list: str = ""  # "ul" | "ol" | ""

    def _close_list():
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = ""

    def _inline(s: str) -> str:
        s = html.escape(s)
        # **bold**
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        # *italic*
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        # `code`
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # [text](url)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   lambda m: f'<a href="{html.escape(m.group(2))}" rel="noopener noreferrer">{m.group(1)}</a>', s)
        return s

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                escaped = html.escape("\n".join(code_buf))
                out.append(f'<pre><code class="lang-{html.escape(code_lang)}">{escaped}</code></pre>')
                code_buf = []; in_code = False; code_lang = ""
            else:
                _close_list()
                in_code = True
                code_lang = line.strip()[3:].strip()
            continue
        if in_code:
            code_buf.append(line); continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            _close_list()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2).strip())}</h{n}>"); continue
        m = re.match(r"^[-*]\s+(.*)", line)
        if m:
            if in_list != "ul": _close_list(); out.append("<ul>"); in_list = "ul"
            out.append(f"<li>{_inline(m.group(1))}</li>"); continue
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            if in_list != "ol": _close_list(); out.append("<ol>"); in_list = "ol"
            out.append(f"<li>{_inline(m.group(1))}</li>"); continue
        if not line.strip():
            _close_list()
            out.append(""); continue
        _close_list()
        out.append(f"<p>{_inline(line)}</p>")
    if in_code:
        escaped = html.escape("\n".join(code_buf))
        out.append(f"<pre><code>{escaped}</code></pre>")
    _close_list()
    return "\n".join(out)


_SRCDOC_WRAPPER = """<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:;">
<style>
  html, body { margin:0; padding:16px; background:#1a1a1a; color:#e5e5e5; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; line-height:1.5; font-size:13px; }
  pre { background:#111; padding:10px; border-radius:6px; overflow:auto; white-space:pre-wrap; word-break:break-all; font-size:11px; }
  code { background:rgba(255,255,255,0.08); padding:1px 4px; border-radius:3px; font-family:ui-monospace,Menlo,monospace; font-size:11px; }
  pre code { background:transparent; padding:0; }
  h1,h2,h3,h4 { color:#fff; }
  a { color:#d97757; text-decoration:underline; }
  svg { max-width:100%; height:auto; }
  img { max-width:100%; height:auto; }
  table { border-collapse:collapse; }
  th,td { border:1px solid #333; padding:4px 8px; }
</style>
</head><body>
%BODY%
</body></html>"""


def _render_srcdoc(kind: str, text: str) -> str:
    if kind == "html":
        body = _sanitize_html(text)
    elif kind == "svg":
        body = _sanitize_html(text)  # SVG 도 같은 필터 적용
    elif kind == "markdown":
        body = _md_to_safe_html(text)
    elif kind == "json":
        try:
            parsed = json.loads(text)
            pretty = html.escape(json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception:
            pretty = html.escape(text)
        body = f'<pre><code class="lang-json">{pretty}</code></pre>'
    else:  # text
        body = f"<pre>{html.escape(text)}</pre>"
    return _SRCDOC_WRAPPER.replace("%BODY%", body)


# ───────── 공개 API ─────────

def api_artifacts_list(_q: dict | None = None) -> dict:
    """최근 run 중 output 이 있는 것들을 meta 리스트로 반환."""
    store = _load_all()
    runs = store.get("runs") or {}
    wfs = store.get("workflows") or {}
    items = []
    for rid, r in runs.items():
        nrs = r.get("nodeResults") or {}
        # output 노드가 있고 status ok 인지 확인
        output_text = ""
        for nid, nr in nrs.items():
            if not isinstance(nr, dict):
                continue
            if nr.get("status") == "ok" and nr.get("output"):
                output_text = nr["output"]  # 마지막 것이 우선
        if not output_text:
            continue
        wf = wfs.get(r.get("workflowId", "")) or {}
        items.append({
            "runId": rid,
            "workflowId": r.get("workflowId", ""),
            "workflowName": wf.get("name", "Untitled"),
            "status": r.get("status", ""),
            "finishedAt": r.get("finishedAt", 0),
            "outputLen": len(output_text),
            "formatHint": _detect_format(output_text),
        })
    items.sort(key=lambda x: x.get("finishedAt", 0), reverse=True)
    return {"ok": True, "items": items[:50]}


def api_artifacts_render(query: dict | None = None) -> dict:
    """특정 run 의 output 을 sanitized HTML (srcdoc) 로 반환.

    query: {runId, format?: auto|html|svg|markdown|json|text}
    """
    rid = ""
    fmt = "auto"
    if isinstance(query, dict):
        v = query.get("runId")
        rid = v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else "")
        fv = query.get("format")
        fmt = fv[0] if isinstance(fv, list) and fv else (fv if isinstance(fv, str) else "auto")
    if not rid:
        return {"ok": False, "error": "runId required"}
    store = _load_all()
    run = (store.get("runs") or {}).get(rid)
    if not run:
        return {"ok": False, "error": "run not found"}
    text = ""
    for nid, nr in (run.get("nodeResults") or {}).items():
        if isinstance(nr, dict) and nr.get("status") == "ok" and nr.get("output"):
            text = nr["output"]
    if not text:
        return {"ok": False, "error": "no output"}
    if fmt == "auto" or fmt not in ("html", "svg", "markdown", "json", "text"):
        fmt = _detect_format(text)
    try:
        srcdoc = _render_srcdoc(fmt, text)
    except Exception as e:
        log.exception("artifact render failed: %s", e)
        return {"ok": False, "error": f"render failed: {e}"}
    return {
        "ok": True,
        "runId": rid,
        "format": fmt,
        "srcdoc": srcdoc,
        "rawLen": len(text),
    }
