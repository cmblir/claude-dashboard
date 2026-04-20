.PHONY: help i18n-refresh i18n-verify i18n-scan run dev

help:
	@echo "Targets:"
	@echo "  i18n-refresh  — audit → build → verify → runtime scan"
	@echo "  i18n-verify   — verify-translations.js 만 실행 (0 miss 체크)"
	@echo "  i18n-scan     — runtime_ko_scan.py 만 실행 (한글 잔존 체크)"
	@echo "  run           — python3 server.py (127.0.0.1:8080)"
	@echo "  dev           — LOG_LEVEL=DEBUG 로 서버 실행"

i18n-refresh:
	bash scripts/translate-refresh.sh

i18n-verify:
	node scripts/verify-translations.js

i18n-scan:
	python3 tools/runtime_ko_scan.py

run:
	python3 server.py

dev:
	LOG_LEVEL=DEBUG python3 server.py
