#!/usr/bin/env bash
# 번역 파이프라인 단일 진입점.
#
#   1) dist/index.html 에서 한국어 phrase 추출 → translation-audit.json
#   2) tools/translations_manual.py 와 병합 → dist/locales/{ko,en,zh}.json
#   3) 누락 0건 검증 (scripts/verify-translations.js)
#   4) 런타임 시뮬레이터로 한글 잔존 0건 검증 (tools/runtime_ko_scan.py)
#
# 실패 시 exit code != 0 로 종료. CI 에서도 그대로 사용.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "▶ [1/4] 한국어 phrase 추출"
python3 tools/extract_ko_strings.py

echo "▶ [2/4] locale JSON 재생성"
PYTHONPATH=tools python3 tools/build_locales.py

echo "▶ [3/4] 번역 누락 검증"
node scripts/verify-translations.js

echo "▶ [4/4] 런타임 한글 잔존 검증"
python3 tools/runtime_ko_scan.py

echo
echo "✅ Translation pipeline completed"
