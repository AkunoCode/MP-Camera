#!/usr/bin/env bash
# Hook wrapper for PreToolUse on git commit
# Input: tool call JSON on stdin with 'command' field

read input
cmd=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('command',''))")

if [[ "$cmd" == *"git commit"* ]]; then
  bash scripts/pre_commit_check.sh
fi
