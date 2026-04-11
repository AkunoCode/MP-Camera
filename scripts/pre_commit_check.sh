#!/usr/bin/env bash
# Pre-commit gate: py_compile + silent-except check on staged .py files
# Exit non-zero to block the commit.

set -euo pipefail

PYTHON="${PYTHON:-python3}"
# Use venv python if available
if [ -f ".venv311/bin/python" ]; then
  PYTHON=".venv311/bin/python"
fi

# Get staged .py files
STAGED=$(git diff --cached --name-only --diff-filter=ACM -- "*.py" 2>/dev/null || true)

if [ -z "$STAGED" ]; then
  echo "✓ No staged Python files to check."
  exit 0
fi

ERRORS=0

echo "Checking staged Python files..."

for f in $STAGED; do
  # py_compile check
  if ! $PYTHON -m py_compile "$f" 2>/dev/null; then
    echo "  ✗ Syntax error: $f"
    $PYTHON -m py_compile "$f" 2>&1 | sed 's/^/    /'
    ERRORS=$((ERRORS + 1))
  fi
done

# Silent except check: look for `except` followed by block containing only `pass`
SILENT_EXCEPTS=$(grep -rn --include="*.py" -A1 "except" $STAGED | grep -B1 "^\s*pass$" | grep "except" || true)

if [ -n "$SILENT_EXCEPTS" ]; then
  echo ""
  echo "  ✗ Silent except blocks found (except + pass with no logging):"
  echo "$SILENT_EXCEPTS" | sed 's/^/    /'
  ERRORS=$((ERRORS + 1))
fi

if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo "✗ Pre-commit check failed. Fix the issues above before committing."
  exit 1
fi

echo "✓ py_compile OK, no silent excepts — proceeding with commit."
exit 0
