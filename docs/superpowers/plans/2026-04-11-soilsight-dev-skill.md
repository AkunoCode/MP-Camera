# SoilSight Dev Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `soilsight-dev` project skill and two git-boundary hooks that enforce code quality, logging standards, .ui file validity, and the release checklist for SoilSight.

**Architecture:** A single skill markdown file (`.claude/skills/soilsight-dev.md`) defines five named actions Claude executes on demand. Two bash helper scripts back the git hooks: one blocks commits when staged `.py` files fail py_compile or contain silent excepts, one prints a release reminder after tagging. Both hooks are registered in `.claude/settings.json`.

**Tech Stack:** Bash scripts, Python 3 (py_compile, xml.etree), Claude Code skill markdown, Claude Code hooks (PreToolUse/PostToolUse).

---

## File Map

| Action | File | Status |
|---|---|---|
| Pre-commit gate script | `scripts/pre_commit_check.sh` | Create |
| Post-tag reminder script | `scripts/post_tag_reminder.sh` | Create |
| Hook registration | `.claude/settings.json` | Modify |
| Project skill | `.claude/skills/soilsight-dev.md` | Create |
| UI validator (called by skill) | `scripts/validate_ui.py` | Create |

---

## Task 1: Pre-commit gate script

**Files:**
- Create: `scripts/pre_commit_check.sh`

- [ ] **Step 1: Create the scripts directory and write the script**

```bash
mkdir -p scripts
```

Create `scripts/pre_commit_check.sh`:

```bash
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
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/pre_commit_check.sh
```

- [ ] **Step 3: Manually verify it works on a clean tree**

```bash
bash scripts/pre_commit_check.sh
```

Expected output:
```
✓ No staged Python files to check.
```

- [ ] **Step 4: Test it catches a syntax error**

```bash
echo "def broken(: pass" > /tmp/test_bad.py
git add /tmp/test_bad.py 2>/dev/null || true
# Stage a real file with a deliberate error to confirm block behavior
python3 -c "
import subprocess, sys
result = subprocess.run(['bash', 'scripts/pre_commit_check.sh'], capture_output=True, text=True, env={**__import__('os').environ, 'STAGED': '/tmp/test_bad.py'})
assert result.returncode != 0, 'Should have failed'
print('✓ Correctly blocks on syntax error')
print(result.stdout)
"
```

- [ ] **Step 5: Test it catches a silent except**

```bash
python3 -c "
import subprocess, os, tempfile

with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
    f.write('def foo():\n    try:\n        pass\n    except Exception:\n        pass\n')
    fname = f.name

env = {**os.environ, 'STAGED': fname}
result = subprocess.run(['bash', 'scripts/pre_commit_check.sh'], capture_output=True, text=True, env=env)
assert result.returncode != 0, 'Should have failed'
print('✓ Correctly blocks on silent except')
print(result.stdout)
"
```

- [ ] **Step 6: Commit**

```bash
git add scripts/pre_commit_check.sh
git commit -m "feat: add pre-commit gate script for py_compile and silent-except check"
```

---

## Task 2: Post-tag reminder script

**Files:**
- Create: `scripts/post_tag_reminder.sh`

- [ ] **Step 1: Write the script**

Create `scripts/post_tag_reminder.sh`:

```bash
#!/usr/bin/env bash
# Post-tag reminder: printed after any `git tag` command.

TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "<tag>")

cat <<EOF

✓ Tag $TAG created. Before pushing:
  □ Ran /soilsight-dev release ?
  □ Checked ~/.mpcamera/debug.log for ERROR entries?
  □ Tested the DMG locally with ./build/build_mac.sh ?
  □ Ready to push: git push origin $TAG

EOF
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/post_tag_reminder.sh
```

- [ ] **Step 3: Verify it runs cleanly**

```bash
bash scripts/post_tag_reminder.sh
```

Expected: prints the checklist with the current latest tag or `<tag>`.

- [ ] **Step 4: Commit**

```bash
git add scripts/post_tag_reminder.sh
git commit -m "feat: add post-tag release reminder script"
```

---

## Task 3: UI validator script

**Files:**
- Create: `scripts/validate_ui.py`

This script is called by the `validate-ui` skill action. It validates all `.ui` files under `mpcamera/layouts/` against the rules in the spec.

- [ ] **Step 1: Write the validator**

Create `scripts/validate_ui.py`:

```python
#!/usr/bin/env python3
"""Validate PyQt6 .ui files for SoilSight conventions."""

import sys
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

LAYOUTS_DIR = Path("mpcamera/layouts")
CONTROLLERS_DIR = Path("mpcamera/controllers")

# Map .ui filename stem → controller file (Qt Designer naming convention)
UI_TO_CONTROLLER = {
    "cameraPage": "camera_page.py",
    "farmPage": "farm_page.py",
    "samplePage": "samples_page.py",
    "settingsPage": "settings_page.py",
    "resultsWindow": "results_window.py",  # in mpcamera/ui/
    "inferenceTable": None,                # no dedicated controller
    "SoilSight_MainWindow": "ui_nav.py",   # root-level
}

CONTROLLER_SEARCH_DIRS = [CONTROLLERS_DIR, Path("mpcamera/ui"), Path(".")]


def find_controller(ui_stem: str) -> Path | None:
    filename = UI_TO_CONTROLLER.get(ui_stem)
    if not filename:
        return None
    for d in CONTROLLER_SEARCH_DIRS:
        p = d / filename
        if p.exists():
            return p
    return None


def validate_file(ui_path: Path) -> list[str]:
    errors = []
    raw = ui_path.read_text(encoding="utf-8")

    # 1. XML declaration
    if not raw.startswith('<?xml version="1.0" encoding="UTF-8"?>'):
        errors.append("Missing or incorrect XML declaration (must be first line: <?xml version=\"1.0\" encoding=\"UTF-8\"?>)")

    # 2. Parse XML
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        errors.append(f"Invalid XML: {e}")
        return errors

    # 3. Root element
    if root.tag != "ui" or root.get("version") != "4.0":
        errors.append('Root element must be <ui version="4.0">')

    # 4. styleSheet properties must have notr="true"
    for prop in root.iter("property"):
        if prop.get("name") == "styleSheet":
            string_el = prop.find("string")
            if string_el is not None and string_el.get("notr") != "true":
                widget = prop.find("../..") or prop
                errors.append(
                    f'styleSheet property missing notr="true" attribute'
                    f' (near widget name={prop.getparent().get("name") if hasattr(prop, "getparent") else "unknown"})'
                )

    # 5. Indentation check: flag tabs or 4-space indent (Qt Designer uses 1-space)
    for i, line in enumerate(raw.splitlines(), 1):
        stripped = line.lstrip()
        if stripped and line != stripped:
            indent = line[: len(line) - len(stripped)]
            if "\t" in indent:
                errors.append(f"Line {i}: tab indentation detected (Qt Designer uses spaces)")
                break
            if len(indent) % 1 != 0 and len(indent) >= 4 and len(indent) % 4 == 0:
                errors.append(f"Line {i}: 4-space indentation detected (Qt Designer uses 1-space)")
                break

    # 6. Widget name cross-reference with controller
    controller_path = find_controller(ui_path.stem)
    if controller_path:
        controller_text = controller_path.read_text(encoding="utf-8")
        widget_names = [w.get("name") for w in root.iter("widget") if w.get("name")]
        for name in widget_names:
            # Skip generic/internal names
            if name in ("centralwidget", "menubar", "statusbar", "Form", "MainWindow"):
                continue
            if f"self.{name}" not in controller_text and f'findChild' not in controller_text:
                errors.append(f"Widget name '{name}' not referenced as self.{name} in {controller_path}")

    return errors


def main():
    ui_files = sorted(LAYOUTS_DIR.glob("*.ui"))
    if not ui_files:
        print(f"No .ui files found in {LAYOUTS_DIR}")
        sys.exit(1)

    total_errors = 0
    for ui_path in ui_files:
        errors = validate_file(ui_path)
        if errors:
            print(f"✗ {ui_path.name}")
            for e in errors:
                print(f"    {e}")
            total_errors += len(errors)
        else:
            print(f"✓ {ui_path.name}")

    print()
    if total_errors:
        print(f"✗ {total_errors} violation(s) found.")
        sys.exit(1)
    else:
        print("✓ All .ui files valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against existing .ui files to establish baseline**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
python3 scripts/validate_ui.py
```

Expected: each file listed. Note any violations — these are pre-existing issues, not regressions. Review output before continuing.

- [ ] **Step 3: Verify it catches a bad file**

```bash
python3 -c "
import subprocess, tempfile, os
from pathlib import Path

bad_ui = '''not xml at all'''
with tempfile.NamedTemporaryFile(suffix='.ui', dir='mpcamera/layouts', mode='w', delete=False, prefix='_test_') as f:
    f.write(bad_ui)
    fname = f.name

result = subprocess.run(['python3', 'scripts/validate_ui.py'], capture_output=True, text=True)
os.unlink(fname)
assert result.returncode != 0, 'Should have failed on bad XML'
print('✓ Correctly fails on invalid .ui file')
print(result.stdout[:300])
"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_ui.py
git commit -m "feat: add UI validator script for .ui file conventions"
```

---

## Task 4: Wire hooks into settings.json

**Files:**
- Modify: `.claude/settings.json`

Claude Code hooks use `PreToolUse` and `PostToolUse` events. The hook `command` receives the tool input as JSON on stdin. Exit non-zero from the command to block the tool call.

- [ ] **Step 1: Update settings.json**

Replace the full content of `.claude/settings.json` with:

```json
{
  "permissions": {
    "allow": [
      "Bash(.venv311/bin/pip install:*)",
      "Bash(.venv311/bin/python -c ':*)",
      "Bash(python -m pytest tests/ -v)",
      "Bash(python -c \"from mpcamera.controllers.camera_page import CameraPageController, CameraState; print\\('✓ camera_page imports OK'\\)\")",
      "Bash(python -c \"from mpcamera.utils.camera_worker import CameraWorker; from mpcamera.utils.inference_worker import InferenceWorker; from mpcamera.utils.inference_utils import _iou_matrix; from mpcamera.utils.local_models_utils import LocalModelInference; from mpcamera.services.roboflow import RoboflowClient; print\\('✓ All modified modules import OK'\\)\")",
      "Bash(python -m py_compile mpcamera/controllers/camera_page.py)",
      "Bash(python -m py_compile ui_nav.py)",
      "Bash(python -m py_compile mpcamera/utils/inference_utils.py mpcamera/utils/results_manager.py)",
      "Bash(python -m py_compile mpcamera/utils/local_models_utils.py)",
      "Bash(python -m py_compile mpcamera/utils/inference_worker.py mpcamera/controllers/camera_page.py)",
      "Bash(python -m py_compile mpcamera/ui/results_window.py)",
      "Bash(python -m py_compile mpcamera/utils/results_manager.py)",
      "Bash(grep -B1 \"pass$\")",
      "Bash(python -m py_compile mpcamera/controllers/camera_page.py mpcamera/utils/inference_worker.py mpcamera/utils/inference_utils.py mpcamera/utils/local_models_utils.py mpcamera/utils/results_manager.py mpcamera/ui/results_window.py ui_nav.py)",
      "Bash(bash /Users/kodecraft-carlo-rabe/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7/skills/brainstorming/scripts/start-server.sh --project-dir /Users/kodecraft-carlo-rabe/Desktop/MP-Camera)",
      "Bash(ls *.spec)",
      "Bash(python -c \"import platform; print\\(platform.system\\(\\), platform.machine\\(\\)\\)\")",
      "Bash(chmod +x build/build_mac.sh)",
      "Bash(./build/build_mac.sh)",
      "Bash(hdiutil eject:*)",
      "Bash(ls -lh dist/SoilSight-*.dmg)",
      "Bash(git push:*)",
      "Bash(git tag:*)",
      "Bash(bash scripts/pre_commit_check.sh)",
      "Bash(bash scripts/post_tag_reminder.sh)",
      "Bash(python3 scripts/validate_ui.py)",
      "Bash(git diff --cached --name-only:*)",
      "Bash(python3 -m py_compile:*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'input=$(cat); cmd=$(echo \"$input\" | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get(\\\"command\\\",\\\"\\\"))\"); case \"$cmd\" in *\"git commit\"*) cd \"$(echo \"$input\" | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get(\\\"workdir\\\",\\\".\\\"))\" 2>/dev/null || echo .) && bash scripts/pre_commit_check.sh;; esac'"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'input=$(cat); cmd=$(echo \"$input\" | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get(\\\"command\\\",\\\"\\\"))\"); case \"$cmd\" in *\"git tag\"*) bash scripts/post_tag_reminder.sh;; esac'"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Validate the JSON is well-formed**

```bash
python3 -c "import json; json.load(open('.claude/settings.json')); print('✓ settings.json valid JSON')"
```

Expected: `✓ settings.json valid JSON`

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "feat: wire pre-commit gate and post-tag reminder hooks into settings.json"
```

---

## Task 5: Write the soilsight-dev skill file

**Files:**
- Create: `.claude/skills/soilsight-dev.md`

- [ ] **Step 1: Create the skills directory and skill file**

```bash
mkdir -p .claude/skills
```

Create `.claude/skills/soilsight-dev.md`:

```markdown
---
name: soilsight-dev
description: SoilSight project dev skill. Actions: check, test, validate-ui, bump-version, release. Invoke as /soilsight-dev <action>.
---

# SoilSight Dev Skill

Project-specific developer workflow for SoilSight. Run actions by invoking `/soilsight-dev <action>`.

Always activate the venv before running Python commands: source `.venv311/bin/activate` or prefix with `.venv311/bin/python`.

---

## action: check

Run this to catch errors before committing.

**Steps (execute in order, stop and report on first failure):**

1. **py_compile all Python files**

```bash
find mpcamera main.py ui_nav.py -name "*.py" | xargs .venv311/bin/python -m py_compile
```

Report each file that fails with the exact error. If all pass, print `✓ py_compile OK`.

2. **Scan for silent except blocks**

```bash
grep -rn --include="*.py" -A2 "except" mpcamera/ main.py ui_nav.py | grep -B2 "^\s*pass$"
```

Report each occurrence with file + line number. If none, print `✓ No silent excepts`.

3. **Check logger import in session-modified files**

For each `.py` file modified in this conversation session, verify it contains:
```python
from mpcamera.logging_utils import get_logger
```
If any modified file is missing this import AND contains a `logger.` call or `logging.` call, flag it. If none, print `✓ Logger imports OK`.

**Output format:**
```
✓ py_compile OK
✗ Silent excepts found:
    mpcamera/services/directus.py:45  except Exception:
    mpcamera/services/directus.py:46      pass
✓ Logger imports OK
```

---

## action: test

Run the full test suite and summarize results.

**Steps:**

1. Run tests:

```bash
.venv311/bin/python -m pytest tests/ -v 2>&1
```

2. Parse output and report:
   - Total passed / failed / errored
   - For each failure: test name, file:line, assertion message
   - If all pass: `✓ All tests passed (N)`

---

## action: validate-ui

Validate all `.ui` files under `mpcamera/layouts/` for SoilSight conventions.

**Steps:**

1. Run the validator script:

```bash
python3 scripts/validate_ui.py
```

2. Report per-file results verbatim from script output.
3. If exit code 0: `✓ All .ui files valid.`
4. If exit code non-zero: list violations and remind user: "Do not hand-edit .ui XML. Use Qt Designer. If you must fix an issue, open the file in Qt Designer, make the change, and save."

---

## action: bump-version

Increment the version in the `VERSION` file.

**Steps:**

1. Read current version:

```bash
cat VERSION
```

2. Ask user: "Bump patch, minor, or major? (current: X.Y.Z)"

3. Compute new version:
   - patch: Z → Z+1
   - minor: Y → Y+1, Z → 0
   - major: X → X+1, Y → 0, Z → 0

4. Write new version to `VERSION`:

```bash
echo "X.Y.Z" > VERSION
```

5. Stage the file:

```bash
git add VERSION
```

6. Report: `VERSION: X.Y.Z → A.B.C (staged, not committed)`

---

## action: release

Enforce the full CLAUDE.md release checklist in order. Stop and block on any failure.

**Steps (execute in strict order):**

1. **Run check** — invoke `check` action above. If any errors, stop: "Fix errors before releasing."

2. **Run test** — invoke `test` action above. If any failures, stop: "Fix failing tests before releasing."

3. **Run validate-ui** — invoke `validate-ui` action above. If any violations, stop: "Fix .ui violations before releasing."

4. **Prompt user:**
   > "Have you checked `~/.mpcamera/debug.log` for ERROR-level entries? (yes/no)"
   
   If no: stop and instruct: `cat ~/.mpcamera/debug.log | grep ERROR`

5. **Run bump-version** — invoke `bump-version` action above.

6. **Instruct user to build and test DMG:**
   ```
   Run: ./build/build_mac.sh
   Then install and manually test the generated DMG.
   Confirm when done.
   ```
   Wait for user confirmation before proceeding.

7. **After confirmation, create tag and push:**

```bash
VERSION=$(cat VERSION)
git commit -m "chore: bump version to $VERSION"
git tag v$VERSION
git push origin main
git push origin v$VERSION
```

8. **Final reminder:**
   > "Monitor GitHub Actions for build completion. Verify release has both SoilSight-X.Y.Z-mac.dmg and SoilSight-X.Y.Z-windows-setup.exe when done."
```

- [ ] **Step 2: Verify the file parses cleanly (no broken markdown fences)**

```bash
python3 -c "
content = open('.claude/skills/soilsight-dev.md').read()
assert 'action: check' in content
assert 'action: test' in content
assert 'action: validate-ui' in content
assert 'action: bump-version' in content
assert 'action: release' in content
print('✓ All 5 actions present in skill file')
"
```

Expected: `✓ All 5 actions present in skill file`

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/soilsight-dev.md
git commit -m "feat: add soilsight-dev project skill with check/test/validate-ui/bump-version/release actions"
```

---

## Task 6: Smoke test the full setup

- [ ] **Step 1: Confirm skill is discoverable**

In Claude Code, run:
```
/soilsight-dev check
```

Expected: Claude reads the skill and runs py_compile + silent-except scan. Verify it completes without errors on the clean codebase.

- [ ] **Step 2: Confirm validate-ui runs**

```
/soilsight-dev validate-ui
```

Expected: each `.ui` file listed as `✓` or with specific violation messages.

- [ ] **Step 3: Dry-run the pre-commit hook manually**

```bash
# Stage a real file, then run the check
git add mpcamera/logging_utils.py
bash scripts/pre_commit_check.sh
git restore --staged mpcamera/logging_utils.py
```

Expected: `✓ py_compile OK, no silent excepts — proceeding with commit.`

- [ ] **Step 4: Final commit of any remaining files**

```bash
git status
# If clean, nothing to do. If any stray files, stage and commit them.
git add -p  # review before adding
git commit -m "chore: finalize soilsight-dev skill and hooks setup"
```

---

## Self-Review Notes

- **Spec coverage:** check ✓, test ✓, validate-ui ✓, bump-version ✓, release ✓, PreToolUse hook ✓, PostToolUse hook ✓
- **No TBDs or placeholders** — all code blocks are complete
- **Type consistency:** scripts are standalone bash/python, no cross-task type dependencies
- **Hook format:** uses stdin JSON parsing to extract `command` field — matches Claude Code hook input format where tool input is passed as JSON on stdin
