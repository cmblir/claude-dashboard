#!/usr/bin/env python3
"""translation-audit.json + 기존 locale JSON + translations_manual.py
를 병합하여 dist/locales/{ko,en,zh}.json 을 재생성.

우선순위 (같은 키일 때):
  MANUAL_* (translations_manual.py) > 기존 dist/locales/*.json > 한국어 원문 fallback

이 스크립트는 **멱등적**이다:
  - 재실행해도 기존 번역이 지워지지 않는다.
  - MANUAL_* 에서 추가 · 오버라이드 · 삭제한 항목만 갱신된다.

출력:
  - dist/locales/{ko,en,zh}.json
  - translation-review.md (NEEDS_REVIEW 목록)
  - _missing.json (사전에 번역이 비어있는 키 보고 — 0 건이어야 검증 통과)
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


def _load_existing_locale(name: str) -> dict[str, str]:
    fp = LOCALES / f"{name}.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_inline_dict(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(
        r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*:\s*'([^'\\]*(?:\\.[^'\\]*)*)'",
        block,
    ):
        k = m.group(1).replace("\\'", "'").replace("\\\\", "\\")
        v = m.group(2).replace("\\'", "'").replace("\\\\", "\\")
        out[k] = v
    return out


def _legacy_inline_dicts():
    """과거 dist/index.html 인라인 사전이 남아 있으면 보조 소스로 사용.

    최신 소스에는 인라인 사전이 제거됐기 때문에 대부분 빈 dict 를 반환한다.
    """
    if not HTML.exists():
        return {}, {}
    html = HTML.read_text(encoding="utf-8")
    en_m = re.search(r"I18N\.en\s*=\s*\{([\s\S]*?)\};", html)
    zh_m = re.search(r"const\s+zhMap\s*=\s*\{([\s\S]*?)\};", html)
    en = _parse_inline_dict(en_m.group(1)) if en_m else {}
    zh = _parse_inline_dict(zh_m.group(1)) if zh_m else {}
    return en, zh


def build():
    try:
        from translations_manual import MANUAL_EN, MANUAL_ZH, MANUAL_KO, NEEDS_REVIEW  # type: ignore
    except Exception:
        MANUAL_EN, MANUAL_ZH, MANUAL_KO, NEEDS_REVIEW = {}, {}, {}, set()

    # 1) baseline — 기존 locale 파일
    base_en = _load_existing_locale("en")
    base_zh = _load_existing_locale("zh")
    base_ko = _load_existing_locale("ko")

    # 2) legacy — 과거 HTML 인라인 사전 (대부분 빈 dict)
    legacy_en, legacy_zh = _legacy_inline_dicts()

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit_keys = [i["text"] for i in audit["items"]]

    # structured key set: MANUAL_KO + baseline 과 legacy 에서 한국어 아닌 모든 키
    structured = set(MANUAL_KO.keys())
    for d in (base_ko, base_en, base_zh, legacy_en, legacy_zh):
        structured |= {k for k in d if not KO.search(k)}

    # 기존 locale 키 보존하되, 아래 중 하나를 만족하면 STALE 로 간주해 제외:
    #   (1) 현재 audit 에 없고 + MANUAL 에도 없고 + structured 아님 + baseline 에서 identity(KO→KO) 인 경우
    #       → 과거 실수로 추가된 서버 prompt 템플릿 등. 번역 없이 유지해봤자 UI 에 KO 노출만 유발.
    # 그 외에는 유지 (합집합).
    current_set = set(audit_keys) | structured | set(MANUAL_EN) | set(MANUAL_ZH) | set(MANUAL_KO)

    def _is_stale(k: str) -> bool:
        if k in current_set:
            return False
        if not KO.search(k):
            return False  # 구조화 키 등 한글 아닌 키 유지
        en_has_trans = k in base_en and not KO.search(base_en[k])
        zh_has_trans = k in base_zh and not KO.search(base_zh[k])
        if en_has_trans or zh_has_trans:
            return False  # 유효한 번역이 이미 있음 → 유지
        return True  # audit·MANUAL 어디에도 없고 번역도 없음 → stale

    union = set(base_ko) | set(base_en) | set(base_zh) | current_set
    all_keys = sorted(k for k in union if not _is_stale(k))

    ko_out: dict[str, str] = {}
    en_out: dict[str, str] = {}
    zh_out: dict[str, str] = {}

    missing_en: list[str] = []
    missing_zh: list[str] = []

    def _pick(key: str, manual: dict, baseline: dict, legacy: dict, fallback: str):
        if key in manual:
            return manual[key], False
        if key in baseline:
            return baseline[key], False
        if key in legacy:
            return legacy[key], False
        return fallback, True

    for k in all_keys:
        # ko
        if KO.search(k):
            ko_out[k] = k  # identity
        else:
            ko_out[k] = MANUAL_KO.get(k, base_ko.get(k, k))

        en_val, en_miss = _pick(k, MANUAL_EN, base_en, legacy_en, k)
        zh_val, zh_miss = _pick(k, MANUAL_ZH, base_zh, legacy_zh, k)
        en_out[k] = en_val
        zh_out[k] = zh_val
        # 실질 누락 판정: key 가 한글인데 value 에도 한글이 남아있으면 번역 안 된 것
        en_effective_miss = en_miss or (KO.search(k) and KO.search(en_val))
        zh_effective_miss = zh_miss or (KO.search(k) and KO.search(zh_val))
        if en_effective_miss and (KO.search(k) or k in structured):
            missing_en.append(k)
        if zh_effective_miss and (KO.search(k) or k in structured):
            missing_zh.append(k)

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

    MISSING.write_text(
        json.dumps(
            {"missing_en": missing_en, "missing_zh": missing_zh},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    review_items = sorted(NEEDS_REVIEW & set(all_keys))
    lines = [
        "# Translation Review",
        "",
        "> 자동 생성 — 번역 전문가 검수 권장 항목.",
        "> `tools/translations_manual.py::NEEDS_REVIEW` 에 등록된 키로부터 생성.",
        "",
        f"총 {len(review_items)} 건.",
        "",
    ]
    if review_items:
        for k in review_items:
            lines.append(f"- `{k}`")
            if k in en_out:
                lines.append(f"  - EN: {en_out[k]}")
            if k in zh_out:
                lines.append(f"  - ZH: {zh_out[k]}")
    else:
        lines.append("_검수가 필요한 항목이 없습니다._")
    REVIEW.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"Wrote ko.json ({len(ko_out)}) · en.json ({len(en_out)}) · zh.json ({len(zh_out)})"
    )
    print(f"Missing EN: {len(missing_en)}, Missing ZH: {len(missing_zh)}")
    print(f"Review items: {len(review_items)}")
    return missing_en, missing_zh


if __name__ == "__main__":
    build()
