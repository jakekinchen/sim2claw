#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  new-workflow-doc.sh <type> <slug>

Types:
  brief
  executor-log
  review-log
  reviewer-message
  manager-log
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ "$#" -lt 2 ]; then
  usage
  exit 0
fi

type="$1"
raw_slug="$2"
slug="$(printf '%s' "$raw_slug" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '-' | sed 's/^-//; s/-$//')"
date_ymd="$(date +%Y-%m-%d)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(cd "$SCRIPT_DIR/../templates" && pwd)"

case "$type" in
  brief)
    dir="docs/briefs"
    template="$TEMPLATE_DIR/brief.md"
    name_suffix="$slug"
    ;;
  executor-log)
    dir="docs/session-logs"
    template="$TEMPLATE_DIR/executor-session-log.md"
    name_suffix="executor-$slug"
    ;;
  review-log)
    dir="docs/session-logs"
    template="$TEMPLATE_DIR/reviewer-message.md"
    name_suffix="review-$slug"
    ;;
  reviewer-message)
    dir="docs/reviewer-messages"
    template="$TEMPLATE_DIR/reviewer-message.md"
    name_suffix="$slug"
    ;;
  manager-log)
    dir="docs/manager-log"
    template="$TEMPLATE_DIR/manager-log.md"
    name_suffix="$slug"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

mkdir -p "$dir"

max_num="$(
  find "$dir" -maxdepth 1 -type f -name '[0-9][0-9][0-9]-*.md' -print 2>/dev/null |
    sed 's#.*/##; s#^\([0-9][0-9][0-9]\)-.*#\1#' |
    sort -n |
    tail -1
)"

if [ -z "${max_num:-}" ]; then
  next_num="001"
else
  next_num="$(printf '%03d' "$((10#$max_num + 1))")"
fi

out="$dir/$next_num-$name_suffix.md"

if [ -e "$out" ]; then
  printf 'Refusing to overwrite existing file: %s\n' "$out" >&2
  exit 1
fi

if [ ! -f "$template" ]; then
  printf 'Template missing: %s\n' "$template" >&2
  exit 1
fi

title="$(printf '%s' "$slug" | sed 's/[-_]/ /g')"

sed \
  -e "s/{{NUMBER}}/$next_num/g" \
  -e "s/{{DATE}}/$date_ymd/g" \
  -e "s/{{TITLE}}/$title/g" \
  -e "s/{{SLUG}}/$slug/g" \
  "$template" > "$out"

printf '%s\n' "$out"
