#!/usr/bin/env bash
# Hook wrapper for PostToolUse on git tag
# Input: tool call JSON on stdin with 'command' field

read input
cmd=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('command',''))")

if [[ "$cmd" == *"git tag"* ]]; then
  bash scripts/post_tag_reminder.sh
fi
