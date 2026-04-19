#!/usr/bin/env bash
# Claude 워크스페이스 대시보드 — 한 줄 실행 스크립트
# 사용법: ./start.sh
set -e

cd "$(dirname "$0")"

# Python 3.9+ 확인
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 가 설치되어 있지 않습니다."
  echo "   macOS: brew install python3 또는 Xcode Command Line Tools 설치"
  exit 1
fi

PORT="${PORT:-8080}"

# 이미 8080 포트가 점유 중이면 프로세스 정보 출력 후 종료 (안전 — 강제 kill 안 함)
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "⚠️  포트 $PORT 가 이미 사용 중입니다:"
  lsof -i:"$PORT"
  echo
  echo "   기존 프로세스를 종료하려면: lsof -ti:$PORT | xargs kill"
  exit 1
fi

echo "🚀 Claude 워크스페이스 대시보드 시작"
echo "   브라우저에서 열기: http://localhost:$PORT"
echo "   종료: Ctrl+C"
echo

exec python3 server.py
