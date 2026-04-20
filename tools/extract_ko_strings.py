#!/usr/bin/env python3
"""dist/index.html 에서 UI 에 노출되는 한국어 **문구** 를 전수 추출.

전략:
  - 파일 전체에서 <style>...</style>, <!-- ... --> 을 제거한다.
  - 기존 I18N.en / zhMap / _NAV_KEYWORDS 블록을 제외한다.
  - /* ... */ 블록 주석도 제거한다.
  - 파일을 줄 단위로 순회하며 각 줄에서 한국어 phrase 를 추출한다.
  - `^\s*//` 로 시작하는 줄(순수 JS 라인 주석)은 전체를 건너뛴다.
  - phrase 경계: `<`, `>`, `{`, `}`, `` ` ``, `'`, `"`, `$`, `|`, `\\`, `\n`
  - 기존 I18N.en 사전의 한국어 키도 병합한다.

출력: translation-audit.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dist" / "index.html"
OUT = ROOT / "translation-audit.json"

KO = re.compile(r"[\uAC00-\uD7A3]")
PHRASE_BOUNDARIES = set("<>{}`'\"$|\\\n")
NOISE_PREFIXES = ("http://", "https://", "data:", "chrome://", "file://")


def _blank(m):
    return " " * len(m.group(0))


def _extract_korean_phrases_from_line(line: str, line_no: int, out: dict):
    """한 줄에서 한국어 phrase 를 추출."""
    n = len(line)
    i = 0
    while i < n:
        if not KO.match(line[i]):
            i += 1
            continue
        start = i
        while start > 0 and line[start - 1] not in PHRASE_BOUNDARIES:
            start -= 1
        end = i
        while end < n and line[end] not in PHRASE_BOUNDARIES:
            end += 1
        phrase = line[start:end].strip()
        i = max(end, i + 1)
        if not phrase or not KO.search(phrase):
            continue
        # 노이즈 필터
        if any(phrase.startswith(p) for p in NOISE_PREFIXES):
            continue
        # 앞 · 뒤 의미 없는 구두점/공백 제거
        phrase = phrase.strip(" \t,:;")
        if not phrase or not KO.search(phrase):
            continue
        out.setdefault(phrase, []).append(line_no)


def extract():
    html = SRC.read_text(encoding="utf-8")
    work = html

    # 1) <style>...</style> 제거 (길이 유지)
    work = re.sub(r"<style[\s\S]*?</style>", _blank, work)
    # 2) <!-- ... --> 제거
    work = re.sub(r"<!--[\s\S]*?-->", _blank, work)
    # 3) /* ... */ 블록 주석 제거 (JS 안에서만 발생하지만 전역으로 처리해도 무해)
    work = re.sub(r"/\*[\s\S]*?\*/", _blank, work)
    # 4) 기존 사전 블록 제거 (구조 유지)
    work = re.sub(r"I18N\.en\s*=\s*\{[\s\S]*?\};", _blank, work)
    work = re.sub(r"const\s+zhMap\s*=\s*\{[\s\S]*?\};", _blank, work)
    work = re.sub(r"const\s+_NAV_KEYWORDS\s*=\s*\{[\s\S]*?\};", _blank, work)

    phrases: dict[str, list[int]] = {}
    for idx, line in enumerate(work.split("\n"), start=1):
        # 순수 한줄 주석은 스킵
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        # 인라인 주석도 최대한 제거: `//` 이후를 제거하되, 따옴표 쌍 홀수면 유지
        if "//" in line and line.count('"') % 2 == 0 and line.count("'") % 2 == 0:
            # 가장 먼저 등장하는 `//` 가 문자열 밖인 경우만 컷
            # 간단 휴리스틱: `://`, `'//'`, `"//"` 제외
            if "://" not in line:
                line = re.sub(r"\s*//[^\n]*$", "", line)
        _extract_korean_phrases_from_line(line, idx, phrases)

    # 너무 긴 phrase 는 문장부호로 재분할
    def _split_long(s: str) -> list[str]:
        if len(s) <= 120:
            return [s]
        parts = re.split(r"[.!?]\s+|\s{2,}|(?<=다)\s+(?=[A-Z가-힣])", s)
        parts = [p.strip() for p in parts if KO.search(p) and p.strip()]
        return parts or [s]

    refined: dict[str, list[int]] = {}
    for p, lines in phrases.items():
        for sub in _split_long(p):
            refined.setdefault(sub, []).extend(lines)

    # 기존 I18N.en 사전 키 병합
    en_match = re.search(r"I18N\.en\s*=\s*\{([\s\S]*?)\};", html)
    existing_ko_keys: set[str] = set()
    if en_match:
        for m in re.finditer(
            r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*:\s*'([^'\\]*(?:\\.[^'\\]*)*)'",
            en_match.group(1),
        ):
            k = m.group(1).replace("\\'", "'")
            if KO.search(k):
                existing_ko_keys.add(k)
    for k in existing_ko_keys:
        refined.setdefault(k, [])

    items = []
    for text in sorted(refined.keys()):
        items.append(
            {
                "text": text,
                "count": len(refined[text]),
                "sample_lines": sorted(set(refined[text]))[:5],
                "in_existing_en_dict": text in existing_ko_keys,
            }
        )

    OUT.write_text(
        json.dumps(
            {"source": "dist/index.html", "total": len(items), "items": items},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Extracted {len(items)} Korean UI phrases → {OUT}")
    return items


if __name__ == "__main__":
    extract()
