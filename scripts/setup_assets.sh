#!/usr/bin/env bash
set -euo pipefail

FORCE=0
REPO="https://huggingface.co/Supertone/supertonic-3"

while [ $# -gt 0 ]; do
  case "$1" in
    --force|-f) FORCE=1; shift ;;
    --repo) REPO="$2"; shift 2 ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="$ROOT/assets"

echo "voicewright setup_assets"
echo "  repo:   $REPO"
echo "  target: $ASSETS"

if [ -d "$ASSETS" ] && [ "$FORCE" -eq 0 ]; then
  echo "assets/가 이미 존재합니다. 다시 받으려면 --force."
  exit 0
fi
if [ "$FORCE" -eq 1 ] && [ -d "$ASSETS" ]; then
  echo "기존 assets/ 삭제..."
  rm -rf "$ASSETS"
fi

command -v git >/dev/null || { echo "git이 필요합니다." >&2; exit 1; }

echo "git lfs 초기화..."
git lfs install || { echo "git-lfs 설치 필요: https://git-lfs.com" >&2; exit 1; }

echo "Hugging Face 모델 다운로드 (1-2 GB)..."
git clone "$REPO" "$ASSETS"

if [ -d "$ASSETS/voice_styles" ]; then
  echo
  echo "사용 가능한 보이스 프리셋:"
  ls "$ASSETS/voice_styles"/*.json 2>/dev/null | xargs -I{} basename {} | sed 's/^/  - /'
else
  echo "주의: voice_styles 디렉토리 없음."
fi

echo
echo "다음 단계: voicewright doctor"
