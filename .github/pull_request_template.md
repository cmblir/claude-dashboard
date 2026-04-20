# PR

## 변경 요약
<!-- 1-3 문장으로 왜/무엇을 바꿨는지 -->

## 체크리스트

### 공통
- [ ] 로컬에서 `python3 server.py` 구동 확인
- [ ] 번역 외 기능 영향 없음 (회귀 없음)

### 번역(i18n) 관련 변경이 있는 경우 — `dist/index.html` · `dist/locales/**` · `tools/**` 수정 시
- [ ] `bash scripts/translate-refresh.sh` 실행 (audit → build → verify → scan)
- [ ] `node scripts/verify-translations.js` 통과 (0 missing)
- [ ] `python3 tools/runtime_ko_scan.py` 통과 (en/zh 한글 잔존 0 건)
- [ ] 신규 UI 텍스트가 있으면 `tools/translations_manual.py` 에 EN/ZH 번역 추가
- [ ] 검수가 필요한 항목은 `NEEDS_REVIEW` 에 등록

### 서버 API 변경이 있는 경우
- [ ] `python3 -c "import py_compile; py_compile.compile('server/routes.py', doraise=True)"` 통과
- [ ] 주요 API 스모크 (`/api/auth/status`, `/api/skills`, `/api/projects` 등) 200 확인
