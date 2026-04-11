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
