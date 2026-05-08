.PHONY: help i18n-refresh i18n-verify i18n-scan run dev pwa-icons app install-mac uninstall-mac \
        lazyclaw-pack lazyclaw-publish-dry lazyclaw-publish

help:
	@echo "Targets:"
	@echo "  i18n-refresh         — audit → build → verify → runtime scan"
	@echo "  i18n-verify          — verify-translations.js 만 실행 (0 miss 체크)"
	@echo "  i18n-scan            — runtime_ko_scan.py 만 실행 (한글 잔존 체크)"
	@echo "  run                  — python3 server.py (127.0.0.1:19500)"
	@echo "  dev                  — LOG_LEVEL=DEBUG 로 서버 실행"
	@echo "  pwa-icons            — regenerate PWA PNG icons from docs/logo/mascot.svg"
	@echo "  app                  — build dist/LazyClaude.app (macOS bundle)"
	@echo "  install-mac          — build + copy LazyClaude.app to /Applications/"
	@echo "  uninstall-mac        — rm -rf /Applications/LazyClaude.app"
	@echo "  lazyclaw-pack        — npm pack the lazyclaw CLI tarball into ./"
	@echo "  lazyclaw-publish-dry — npm publish --dry-run from src/lazyclaw"
	@echo "  lazyclaw-publish     — npm publish (real, requires npm login)"

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

# Pack the lazyclaw CLI tarball into the repo root (handy for sharing
# pre-publish or for `npm install ./lazyclaw-x.y.z.tgz` style installs).
lazyclaw-pack:
	cd src/lazyclaw && npm pack --pack-destination "$(CURDIR)"
	@ls -1 lazyclaw-*.tgz | tail -1

# Dry-run a publish from the correct subdirectory. Avoids the
# "Cannot read properties of null (reading 'prerelease')" error that
# fires when `npm publish` runs against the root package.json (which
# is private and has no version field).
lazyclaw-publish-dry:
	cd src/lazyclaw && npm publish --dry-run

# Real publish — requires `npm login` first AND a 2FA OTP because
# npmjs.org enforces 2FA on publish. npm's interactive OTP prompt
# doesn't fire reliably when run through Make (the publish PUT goes
# straight out and 403s); pass OTP as a Make variable instead:
#
#   make lazyclaw-publish OTP=123456    # 6 digits from authenticator
#
# Pre-flight refuses uncommitted edits inside src/lazyclaw and a
# missing `npm login`, so each surface fails fast with a clear cause.
lazyclaw-publish:
	@if ! git diff --quiet src/lazyclaw || ! git diff --cached --quiet src/lazyclaw; then \
	  echo "✗ src/lazyclaw has uncommitted changes — commit or stash first"; \
	  exit 1; \
	fi
	@npm whoami >/dev/null 2>&1 || { echo "✗ run \`npm login\` first"; exit 1; }
	@if [ -z "$(OTP)" ]; then \
	  echo "✗ OTP required: make lazyclaw-publish OTP=123456"; \
	  echo "  (open your authenticator app for the 6-digit npm code)"; \
	  echo "  alternative: cd src/lazyclaw && npm publish        # interactive prompt"; \
	  exit 1; \
	fi
	cd src/lazyclaw && npm publish --otp=$(OTP)
