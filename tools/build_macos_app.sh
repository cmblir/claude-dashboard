#!/usr/bin/env bash
# Build LazyClaude.app — a tiny macOS bundle that double-clicks into:
#   1) python3 server.py  (started in the background, logs to ~/Library/Logs/LazyClaude/server.log)
#   2) http://127.0.0.1:8080  opened in the user's default browser
#   3) shuts the server down on Quit (or when /Applications stops the process)
#
# The bundle is just a shell launcher + Info.plist + .icns. No Python interpreter
# is bundled — we depend on the system python3 (LazyClaude itself is stdlib-only).
#
# Usage:
#   tools/build_macos_app.sh                # builds dist/LazyClaude.app
#   APP_OUT=/Applications tools/...sh       # builds straight into /Applications
#   make app                                # same as no-arg form
#   make install-mac                        # build + cp -R to /Applications

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${APP_OUT:-$ROOT/dist}"
APP="$OUT_DIR/LazyClaude.app"
VERSION="$(cat "$ROOT/VERSION" | tr -d '[:space:]')"

echo "▶ building $APP (v$VERSION)"

# ── 1. icns from existing PNGs ──────────────────────────────────────────────
ICNS_TMP="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$ICNS_TMP"
SRC_PNG="$ROOT/dist/icons/icon-512.png"
if [[ ! -f "$SRC_PNG" ]]; then
  echo "  · regenerating PWA icons (need icon-512.png)"
  node "$ROOT/tools/build_pwa_icons.mjs" >/dev/null
fi

# Apple expects 8 sizes (10 with @2x dupes). sips resizes; cp covers the @2x.
declare -a SIZES=(16 32 64 128 256 512 1024)
for s in "${SIZES[@]}"; do
  sips -z "$s" "$s" "$SRC_PNG" --out "$ICNS_TMP/icon_${s}x${s}.png" >/dev/null
done
# @2x variants — Apple's iconutil naming convention
cp "$ICNS_TMP/icon_32x32.png"   "$ICNS_TMP/icon_16x16@2x.png"
cp "$ICNS_TMP/icon_64x64.png"   "$ICNS_TMP/icon_32x32@2x.png"
cp "$ICNS_TMP/icon_256x256.png" "$ICNS_TMP/icon_128x128@2x.png"
cp "$ICNS_TMP/icon_512x512.png" "$ICNS_TMP/icon_256x256@2x.png"
cp "$ICNS_TMP/icon_1024x1024.png" "$ICNS_TMP/icon_512x512@2x.png"
rm -f "$ICNS_TMP/icon_64x64.png" "$ICNS_TMP/icon_1024x1024.png"

# ── 2. bundle skeleton ──────────────────────────────────────────────────────
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

iconutil -c icns "$ICNS_TMP" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$(dirname "$ICNS_TMP")"

# ── 3. Info.plist ───────────────────────────────────────────────────────────
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>                <string>LazyClaude</string>
  <key>CFBundleDisplayName</key>         <string>LazyClaude</string>
  <key>CFBundleIdentifier</key>          <string>app.lazyclaude.dashboard</string>
  <key>CFBundleVersion</key>             <string>${VERSION}</string>
  <key>CFBundleShortVersionString</key>  <string>${VERSION}</string>
  <key>CFBundleExecutable</key>          <string>LazyClaude</string>
  <key>CFBundleIconFile</key>            <string>AppIcon</string>
  <key>CFBundlePackageType</key>         <string>APPL</string>
  <key>CFBundleSignature</key>           <string>????</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>LSMinimumSystemVersion</key>      <string>10.13</string>
  <key>NSHighResolutionCapable</key>     <true/>
  <key>LSApplicationCategoryType</key>   <string>public.app-category.developer-tools</string>
  <key>NSHumanReadableCopyright</key>    <string>LazyClaude — local-first Claude Code dashboard. MIT.</string>
</dict>
</plist>
PLIST

# ── 4. launcher script ──────────────────────────────────────────────────────
LAUNCHER="$APP/Contents/MacOS/LazyClaude"
cat > "$LAUNCHER" <<'SH'
#!/usr/bin/env bash
# LazyClaude .app launcher.
#   - finds the project directory (LAZYCLAUDE_HOME env > ~/Lazyclaude > ~/lazyclaude)
#   - starts python3 server.py in the background
#   - opens the dashboard in the default browser
#   - on receiving SIGTERM/SIGINT (Quit, killall LazyClaude, etc.) it terminates the server too
set -euo pipefail

LOG_DIR="$HOME/Library/Logs/LazyClaude"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/server.log"

# Resolve the LazyClaude project path. Tries:
#   1. $LAZYCLAUDE_HOME (env)
#   2. ~/Lazyclaude
#   3. ~/lazyclaude
#   4. /Applications/LazyClaude.app/../Lazyclaude  (uncommon)
PROJ=""
for cand in "${LAZYCLAUDE_HOME:-}" "$HOME/Lazyclaude" "$HOME/lazyclaude"; do
  if [[ -n "$cand" && -f "$cand/server.py" ]]; then PROJ="$cand"; break; fi
done
if [[ -z "$PROJ" ]]; then
  /usr/bin/osascript -e 'display dialog "LazyClaude project not found.\n\nClone https://github.com/cmblir/LazyClaude into ~/Lazyclaude or set the LAZYCLAUDE_HOME env var, then re-launch." buttons {"OK"} default button "OK" with icon caution with title "LazyClaude"' >/dev/null
  exit 1
fi

cd "$PROJ"

# Ensure python3 is available
if ! command -v python3 >/dev/null 2>&1; then
  /usr/bin/osascript -e 'display dialog "python3 is required but not installed.\n\nInstall via Xcode Command Line Tools:\n  xcode-select --install\n\nOr via Homebrew:\n  brew install python3" buttons {"OK"} default button "OK" with icon caution with title "LazyClaude"' >/dev/null
  exit 1
fi

PORT="${PORT:-8080}"
URL="http://127.0.0.1:$PORT"

# Reuse an already-running server if there is one on PORT.
if curl -sf "$URL/api/version" >/dev/null 2>&1; then
  /usr/bin/open "$URL"
  exit 0
fi

# Start the server.
echo "$(date '+%F %T')  starting LazyClaude server on $URL" >> "$LOG_FILE"
PORT="$PORT" python3 server.py >> "$LOG_FILE" 2>&1 &
SERVER_PID=$!

# Forward Quit/Terminate to the server.
cleanup() {
  echo "$(date '+%F %T')  shutting down (PID $SERVER_PID)" >> "$LOG_FILE"
  if kill -0 "$SERVER_PID" 2>/dev/null; then kill -TERM "$SERVER_PID" 2>/dev/null || true; fi
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Wait for the server to come up (max 10s).
for _ in $(seq 1 40); do
  if curl -sf "$URL/api/version" >/dev/null 2>&1; then break; fi
  sleep 0.25
done

/usr/bin/open "$URL"

# Block on the server so Dock icon stays bouncing/active.
wait "$SERVER_PID"
SH
chmod +x "$LAUNCHER"

# ── 5. summary ──────────────────────────────────────────────────────────────
SIZE=$(du -sh "$APP" | awk '{print $1}')
echo "✅ built $APP ($SIZE)"
echo "   double-click to launch (server logs: ~/Library/Logs/LazyClaude/server.log)"
