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
SERVER_DIR = ROOT / "server"
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
    # 3) /* ... */ 는 여기서 stripping 하지 않는다 — JS 내 문자열 리터럴(예: '/*/memory')
    #    때문에 거대한 false match 가 발생해 중간 컨텐츠를 통째로 삼킬 수 있다.
    #    한줄 주석 `//` 은 라인 단위로 따로 걸러낸다. 블록 주석은 매우 드물고,
    #    남아 있어도 `phrase boundaries` 로 끊어지기 때문에 감사에 큰 문제 없음.
    # 4) 기존 사전 블록 제거 (현재 HTML 에는 없지만 혹시 남아있을 경우 보호)
    work = re.sub(r"I18N\.en\s*=\s*\{[\s\S]*?\};", _blank, work)
    work = re.sub(r"const\s+zhMap\s*=\s*\{[\s\S]*?\};", _blank, work)
    work = re.sub(r"const\s+_NAV_KEYWORDS\s*=\s*\{[\s\S]*?\};", _blank, work)

    phrases: dict[str, list[int]] = {}
    # 정규식 리터럴 전용 노이즈: `/[가-힣]/` 패턴 자체는 UI 문자열 아님
    _regex_literal_noise = re.compile(r"^\s*(?:const|let|var)\s+\w+\s*=\s*/\[.*?\]/.*$")
    for idx, line in enumerate(work.split("\n"), start=1):
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        # 정규식 리터럴 선언 라인만 스킵 (`const _KO_RE = /[가-힣]/` 같은 것)
        if _regex_literal_noise.match(line):
            continue
        # 인라인 주석 제거 (따옴표 짝 · URL 제외)
        if "//" in line and line.count('"') % 2 == 0 and line.count("'") % 2 == 0:
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

    # server/*.py 에서 UI 노출되는 Korean 라벨만 가려낸다.
    # 정책: 길이 ≤ 50 & 개행 없음 & 모듈별 UI-whitelist 에 등장한 경우만.
    # (전체 스캔은 prompt 템플릿·로그 메시지까지 포함해 over-inclusive)
    _UI_MODULES = {"agents.py", "system.py", "device.py", "features.py"}
    if SERVER_DIR.exists():
        for py in sorted(SERVER_DIR.rglob("*.py")):
            if py.name not in _UI_MODULES:
                continue
            try:
                src = py.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in re.finditer(r'"([^"\\\n]*(?:\\.[^"\\\n]*)*)"', src):
                s = m.group(1)
                if not s or not KO.search(s):
                    continue
                if len(s) > 80 or "\\n" in s:
                    continue
                refined.setdefault(s, [])

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
