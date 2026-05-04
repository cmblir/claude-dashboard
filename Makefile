.PHONY: help i18n-refresh i18n-verify i18n-scan run dev pwa-icons app install-mac uninstall-mac

help:
	@echo "Targets:"
	@echo "  i18n-refresh  — audit → build → verify → runtime scan"
	@echo "  i18n-verify   — verify-translations.js 만 실행 (0 miss 체크)"
	@echo "  i18n-scan     — runtime_ko_scan.py 만 실행 (한글 잔존 체크)"
	@echo "  run           — python3 server.py (127.0.0.1:8080)"
	@echo "  dev           — LOG_LEVEL=DEBUG 로 서버 실행"
	@echo "  pwa-icons     — regenerate PWA PNG icons from docs/logo/mascot.svg"
	@echo "  app           — build dist/LazyClaude.app (macOS bundle)"
	@echo "  install-mac   — build + copy LazyClaude.app to /Applications/"
	@echo "  uninstall-mac — rm -rf /Applications/LazyClaude.app"

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

pwa-icons:
	node tools/build_pwa_icons.mjs

app: pwa-icons
	bash tools/build_macos_app.sh

install-mac: app
	@if [ -d /Applications/LazyClaude.app ]; then \
	  echo "▶ replacing existing /Applications/LazyClaude.app"; \
	  rm -rf /Applications/LazyClaude.app; \
	fi
	cp -R dist/LazyClaude.app /Applications/
	@echo "✅ installed to /Applications/LazyClaude.app"
	@echo "   open via Spotlight (⌘Space → 'LazyClaude') or double-click in Finder"

uninstall-mac:
	rm -rf /Applications/LazyClaude.app
	@echo "🗑  removed /Applications/LazyClaude.app"

test:  ## Run pytest unit tests (auto_resume coverage)
	@which pytest >/dev/null 2>&1 || { echo "pytest not installed — pip install pytest"; exit 1; }
	pytest tests/ -v

bench-providers:  ## Throughput benchmark for the SSE parsers (anthropic + openai)
	@echo "▶ anthropic"
	@node scripts/bench-providers.mjs
	@echo "▶ openai"
	@PROVIDER=openai node scripts/bench-providers.mjs
	@echo "▶ anthropic 50k tokens"
	@N=50000 node scripts/bench-providers.mjs
