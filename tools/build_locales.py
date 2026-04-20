#!/usr/bin/env python3
"""translation-audit.json + 기존 HTML 인라인 사전 + translations_manual.py
를 병합해서 dist/locales/{ko,en,zh}.json 을 생성한다.

구조:
  - ko.json : 한국어 원문 → 한국어 원문 (identity)
  - en.json : 한국어 원문 → 영어 번역
  - zh.json : 한국어 원문 → 중국어 번역
  - 구조화 키(`nav.*`, `settings.*` 등) 도 동일하게 3개 파일에 포함.

정책:
  - 한국어 원문이 누락된 경우: EMPTY string 대신 FALLBACK=원문 유지 + _missing.json 에 기록
  - _needs_review 는 translation-review.md 에 별도로 기록 (manual dict 에서 지정)

출력 부가:
  - translation-review.md : 검수 권장 항목 목록
  - _missing.json        : 사전에서 누락된 키 보고 (0 건이어야 검증 통과)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "dist" / "index.html"
AUDIT = ROOT / "translation-audit.json"
LOCALES = ROOT / "dist" / "locales"
REVIEW = ROOT / "translation-review.md"
MISSING = ROOT / "_missing.json"

KO = re.compile(r"[\uAC00-\uD7A3]")


def _parse_dict_literal(block: str) -> dict[str, str]:
    """JS 객체 리터럴에서 'key':'value' 쌍 파싱."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*:\s*'([^'\\]*(?:\\.[^'\\]*)*)'",
        block,
    ):
        key = m.group(1).encode().decode("unicode_escape") if "\\" in m.group(1) else m.group(1)
        key = m.group(1).replace("\\'", "'").replace("\\\\", "\\")
        val = m.group(2).replace("\\'", "'").replace("\\\\", "\\")
        out[key] = val
    return out


def _extract_existing_dicts():
    html = HTML.read_text(encoding="utf-8")
    en_m = re.search(r"I18N\.en\s*=\s*\{([\s\S]*?)\};", html)
    zh_m = re.search(r"const\s+zhMap\s*=\s*\{([\s\S]*?)\};", html)
    en = _parse_dict_literal(en_m.group(1)) if en_m else {}
    zh = _parse_dict_literal(zh_m.group(1)) if zh_m else {}
    return en, zh


def build():
    # manual overrides / additions
    try:
        from translations_manual import MANUAL_EN, MANUAL_ZH, NEEDS_REVIEW  # type: ignore
    except Exception:
        MANUAL_EN, MANUAL_ZH, NEEDS_REVIEW = {}, {}, set()

    en_existing, zh_existing = _extract_existing_dicts()

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit_keys = [i["text"] for i in audit["items"]]

    # 구조화 키 (nav.*, settings.* 등) — 기존 사전에서 한국어 아닌 모든 키 수집
    structured_keys = [k for k in (set(en_existing) | set(zh_existing)) if not KO.search(k)]

    all_keys = sorted(set(audit_keys) | set(structured_keys))

    ko_out: dict[str, str] = {}
    en_out: dict[str, str] = {}
    zh_out: dict[str, str] = {}

    missing_en: list[str] = []
    missing_zh: list[str] = []

    for k in all_keys:
        # ko: 구조화 키는 MANUAL_KO 우선, 아니면 키 그대로. 한국어 원문 키는 identity.
        if KO.search(k):
            ko_out[k] = k
        else:
            # 구조화 키 (예: nav.overview) — MANUAL_KO 에서 ko 라벨 제공
            ko_out[k] = MANUAL_EN.get(k, k)  # 당장은 영어/원문 사용; 개별 override 가능

        # en: 우선순위 MANUAL_EN → en_existing → 누락
        if k in MANUAL_EN:
            en_out[k] = MANUAL_EN[k]
        elif k in en_existing:
            en_out[k] = en_existing[k]
        else:
            en_out[k] = k  # fallback: 원문 유지 (ko 노출 위험)
            missing_en.append(k)

        # zh: 우선순위 MANUAL_ZH → zh_existing → 누락
        if k in MANUAL_ZH:
            zh_out[k] = MANUAL_ZH[k]
        elif k in zh_existing:
            zh_out[k] = zh_existing[k]
        else:
            zh_out[k] = k  # fallback: 원문 유지
            missing_zh.append(k)

    # 구조화 키의 한국어 라벨은 KO 사전에서 구조화 키를 실제 한국어로 바꿔 노출
    # (ko.json 은 화면 표시용이 아니고 기본값 제공용 — 대부분 identity)
    # 구조화 키는 MANUAL_KO 에서 override 가능
    try:
        from translations_manual import MANUAL_KO  # type: ignore
    except Exception:
        MANUAL_KO = {}
    for k, v in MANUAL_KO.items():
        ko_out[k] = v

    LOCALES.mkdir(parents=True, exist_ok=True)
    (LOCALES / "ko.json").write_text(
        json.dumps(ko_out, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (LOCALES / "en.json").write_text(
        json.dumps(en_out, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (LOCALES / "zh.json").write_text(
        json.dumps(zh_out, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # missing 보고
    MISSING.write_text(
        json.dumps(
            {"missing_en": missing_en, "missing_zh": missing_zh},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 검수 목록
    review_items = sorted(NEEDS_REVIEW & set(all_keys))
    lines = [
        "# Translation Review",
        "",
        "> 자동 생성 — 번역 전문가 검수가 필요한 항목 목록.",
        "> `tools/translations_manual.py::NEEDS_REVIEW` 에 등록된 키를 기반으로 생성됨.",
        "",
        f"총 {len(review_items)} 건.",
        "",
    ]
    for k in review_items:
        lines.append(f"- `{k}`")
        if k in en_out:
            lines.append(f"  - EN: {en_out[k]}")
        if k in zh_out:
            lines.append(f"  - ZH: {zh_out[k]}")
    REVIEW.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"Wrote ko.json ({len(ko_out)}) · en.json ({len(en_out)}) · zh.json ({len(zh_out)})"
    )
    print(f"Missing EN: {len(missing_en)}, Missing ZH: {len(missing_zh)}")
    print(f"Review items: {len(review_items)}")
    return missing_en, missing_zh


if __name__ == "__main__":
    build()
