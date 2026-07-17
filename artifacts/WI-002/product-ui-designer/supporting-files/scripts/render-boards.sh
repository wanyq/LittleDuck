#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
SUPPORT="$ROOT/runs/WI-002/product-ui-designer/supporting-files"
CHROME=${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}

test -x "$CHROME" || { echo "Chrome not executable: $CHROME"; exit 1; }

"$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --allow-file-access-from-files --window-size=1680,3200 \
  --screenshot="$SUPPORT/h5-visual-board.png" \
  "file://$SUPPORT/h5-visual-board.html"

"$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --allow-file-access-from-files --window-size=1800,5900 \
  --screenshot="$SUPPORT/admin-visual-board.png" \
  "file://$SUPPORT/admin-visual-board.html"

echo "Rendered H5 and admin visual boards."
