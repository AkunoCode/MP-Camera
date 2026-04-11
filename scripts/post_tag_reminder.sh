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
