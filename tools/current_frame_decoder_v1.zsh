#!/bin/zsh
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  print -u2 "usage: current_frame_decoder_v1.zsh SOURCE_VIDEO OUTPUT_PNG"
  exit 64
fi

exec /opt/homebrew/bin/ffmpeg \
  -v error \
  -nostdin \
  -i "$1" \
  -map 0:v:0 \
  -vf 'select=eq(n\,29)' \
  -frames:v 1 \
  -fps_mode passthrough \
  "$2"
