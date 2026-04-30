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

# v2.46.0 — mtime guard: skip the 1.7s pipeline if no source file is newer
# than translation-audit.json. Saves time in CI / pre-commit hooks.
# Force a rebuild with: FORCE=1 ./scripts/translate-refresh.sh
if [ "${FORCE:-0}" != "1" ] && [ -f translation-audit.json ]; then
  if ! find dist/index.html server tools/translations_manual.py tools/translations_manual_*.py \
       -newer translation-audit.json -print -quit 2>/dev/null | grep -q .; then
    echo "✅ skipped — no source changes since last translation-audit.json"
    exit 0
  fi
fi

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
