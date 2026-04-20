#!/usr/bin/env python3
"""런타임 DOM 번역 시뮬레이터 — 한글 잔존 0 건 검증.

dist/index.html 에 dist/locales/{en,zh}.json 을 적용했을 때
실제 브라우저 런타임과 동일한 규칙으로 DOM 텍스트가 번역되는지 확인한다.
한글이 단 한 글자라도 남으면 exit 1.

시뮬레이션 규칙 — dist/index.html 의 `_translateDOM` 과 동등:
  1) 텍스트 노드 trim 후 전체 일치 dict 키면 그대로 교체
  2) 아니면 길이 내림차순으로 5+ 글자 키를 substring 교체 반복
  3) placeholder · title · alt · aria-label 속성값도 같은 규칙으로 교체
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "dist" / "index.html"
LOCALES = ROOT / "dist" / "locales"

KO = re.compile(r"[\uAC00-\uD7A3]")


_HANGUL_BOUNDARY_CACHE: dict = {}


def _apply_translation(text: str, dict_: dict, sorted_keys: list) -> str:
    """_translateDOM 과 동일한 번역 규칙 (파이썬 포팅).

    - 전체 일치 우선
    - 아니면 긴 키부터 순차 치환
    - 짧은 키(≤4)는 Hangul word-boundary 로 보호
    """
    trimmed = text.strip()
    if trimmed and trimmed in dict_:
        return text.replace(trimmed, dict_[trimmed], 1)
    out = text
    for k in sorted_keys:
        if k not in out:
            continue
        if len(k) >= 5:
            out = out.replace(k, dict_[k])
        else:
            pat = _HANGUL_BOUNDARY_CACHE.get(k)
            if pat is None:
                pat = re.compile(
                    r"(?<![\uAC00-\uD7A3])" + re.escape(k) + r"(?![\uAC00-\uD7A3])"
                )
                _HANGUL_BOUNDARY_CACHE[k] = pat
            out = pat.sub(dict_[k], out)
    return out


def _extract_translatable(html: str):
    """HTML 에서 런타임이 번역 대상으로 삼는 텍스트 노드 + 속성값을 (kind, text, line) 목록으로 반환.

    <style>, <!-- -->, <script> 는 제외 (script 는 t() 호출 경로로 별도 검증됨).
    """
    cleaned = re.sub(r"<style[\s\S]*?</style>", lambda m: " " * len(m.group(0)), html)
    cleaned = re.sub(r"<!--[\s\S]*?-->", lambda m: " " * len(m.group(0)), cleaned)
    cleaned = re.sub(
        r"<script[\s\S]*?</script>", lambda m: " " * len(m.group(0)), cleaned
    )

    items = []
    # 텍스트 노드
    for m in re.finditer(r">([^<>]*)<", cleaned):
        raw = m.group(1)
        if not KO.search(raw):
            continue
        line = cleaned.count("\n", 0, m.start(1)) + 1
        for piece in raw.split("\n"):
            t = piece.strip()
            if t and KO.search(t):
                items.append(("text", t, line))
    # 속성
    for attr in ("placeholder", "title", "alt", "aria-label"):
        for re_ in (
            re.compile(rf'{attr}\s*=\s*"([^"]*)"', re.IGNORECASE),
            re.compile(rf"{attr}\s*=\s*'([^']*)'", re.IGNORECASE),
        ):
            for m in re_.finditer(cleaned):
                v = m.group(1)
                if KO.search(v):
                    line = cleaned.count("\n", 0, m.start(1)) + 1
                    items.append((f"attr[{attr}]", v.strip(), line))
    return items


def _extract_t_calls(html: str):
    """<script> 블록 안의 t('한국어') 호출 인자 수집."""
    out = []
    scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", html)
    for s in scripts:
        for m in re.finditer(r"\bt\(\s*(['\"`])((?:\\.|(?!\1).)*?)\1\s*\)", s):
            raw = m.group(2)
            if KO.search(raw):
                out.append(raw.replace("\\'", "'").replace('\\"', '"'))
    return out


def scan_lang(lang: str, html: str) -> int:
    fp = LOCALES / f"{lang}.json"
    d = json.loads(fp.read_text(encoding="utf-8"))
    sorted_keys = sorted(
        (k for k in d if KO.search(k)), key=lambda x: -len(x)
    )
    residue_static = []  # (kind, original, after_translate, line)
    for kind, txt, line in _extract_translatable(html):
        after = _apply_translation(txt, d, sorted_keys)
        if KO.search(after):
            residue_static.append((kind, txt, after, line))

    residue_dynamic = []  # (original, translated)
    for raw in _extract_t_calls(html):
        val = d.get(raw, raw)
        if KO.search(val):
            residue_dynamic.append((raw, val))

    print(f"\n=== [{lang}] ===")
    print(f"static nodes with Korean residue: {len(residue_static)}")
    if residue_static:
        for kind, orig, after, line in residue_static[:10]:
            print(f"  L{line} {kind}")
            print(f"    orig   : {orig[:80]}")
            print(f"    after  : {after[:80]}")
    print(f"t() calls with Korean residue: {len(residue_dynamic)}")
    if residue_dynamic:
        for o, a in residue_dynamic[:10]:
            print(f"    {o!r} → {a!r}")

    return len(residue_static) + len(residue_dynamic)


def main() -> int:
    html = HTML.read_text(encoding="utf-8")
    total = 0
    for lang in ("en", "zh"):
        total += scan_lang(lang, html)
    print(
        f"\n총 한글 잔존: {total} 건 — {'통과' if total == 0 else 'FAIL'}"
    )
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
