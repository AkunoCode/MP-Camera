# SoilSight Dev Skill & Hooks Design

**Date:** 2026-04-11  
**Status:** Approved

---

## Overview

A single project skill (`soilsight-dev`) with named actions that cover the 5 key developer pain points, plus two git-boundary hooks in `.claude/settings.json`. No hooks on every file edit — only at git commit and tag boundaries.

---

## Skill

**Location:** `.claude/skills/soilsight-dev.md`  
**Invocation:** `/soilsight-dev <action>`

### Actions

#### `check`
- Run `python -m py_compile` on all `.py` files under `mpcamera/` and root-level (`main.py`, `ui_nav.py`)
- Scan all `.py` files for `except` blocks that contain only `pass` (silent error swallowing)
- Verify that any `.py` file modified in the current session imports `get_logger` from `mpcamera.logging_utils`
- Report: list of compile errors, list of silent-except locations, list of files missing logger import

#### `test`
- Run `python -m pytest tests/ -v` inside the `.venv311` virtualenv
- Summarize: pass count, fail count, any ERROR-level tracebacks
- On failure, highlight the specific assertion and file so the user can navigate directly

#### `validate-ui`
- Parse each `.ui` file under `mpcamera/layouts/` as XML
- Check: valid XML with `<?xml version="1.0" encoding="UTF-8"?>` declaration
- Check: `<ui version="4.0">` root element present
- Check: all `styleSheet` string properties have `notr="true"` attribute
- Check: indentation is consistent (Qt Designer uses 1-space indent — flag tabs or 2/4-space deviations introduced by hand-editing)
- Check: no widget `name` attributes that reference non-existent controller attributes — match by filename convention (`cameraPage.ui` → `mpcamera/controllers/camera_page.py`) and grep for `self.<widgetName>` in the paired controller; report widget names present in the `.ui` but absent from the controller
- Report: per-file list of violations; clean files listed as OK

#### `bump-version`
- Read current version from `VERSION` file
- Accept argument: `patch` (default), `minor`, or `major`
- Increment the appropriate semver component
- Write updated version back to `VERSION`
- Stage `VERSION` with `git add VERSION`
- Report: old version → new version

#### `release`
Enforces the CLAUDE.md release checklist in strict order:
1. Run `check` — block if any errors
2. Run `test` — block if any failures
3. Run `validate-ui` — block if any violations
4. Prompt user: "Have you checked `~/.mpcamera/debug.log` for ERROR entries?"
5. Run `bump-version` (ask patch/minor/major if not provided)
6. Instruct user to run `./build/build_mac.sh` and test the DMG manually
7. After user confirms DMG is good, run `git tag vX.Y.Z && git push origin vX.Y.Z`
8. Remind user to monitor GitHub Actions at the repo's Actions page

---

## Hooks

**Location:** `.claude/settings.json` (project-level)

### Hook 1: PreToolUse — git commit gate

**Trigger:** Any `Bash` tool call whose command matches `git commit`

**Action:**
- Identify staged `.py` files (`git diff --cached --name-only --diff-filter=ACM "*.py"`)
- Run `python -m py_compile` on each staged `.py` file
- Scan staged `.py` files for `except` + `pass` silent-error pattern
- If any check fails: print a blocking error message listing the offending files and exit non-zero to cancel the commit
- If all pass: print "✓ py_compile OK, no silent excepts — proceeding with commit"

### Hook 2: PostToolUse — git tag reminder

**Trigger:** Any `Bash` tool call whose command matches `git tag`

**Action:**
- Print a reminder checklist:
  ```
  ✓ Tag created. Before pushing:
  □ Ran /soilsight-dev release?
  □ Checked ~/.mpcamera/debug.log for ERRORs?
  □ Tested the DMG locally?
  □ Ready to push: git push origin <tag>
  ```

---

## File Structure

```
.claude/
  settings.json          ← hooks config (PreToolUse + PostToolUse)
  skills/
    soilsight-dev.md     ← project skill with all actions
```

---

## Out of Scope

- Hooks on every file save/edit (intentionally excluded to avoid noise)
- Windows build pipeline (macOS only for now)
- Auto-formatting `.ui` files (Qt Designer is authoritative; we only validate, never rewrite)
