#!/usr/bin/env bash
# Render data/contributions.csv into docs/.
#
# With no arguments it refreshes every image the README embeds: all three
# styles in both themes. No network and no token, so re-run it as often as you
# like while tuning.
#
# Any argument switches to a single explicit render instead, with the flags
# passed straight through to spiral.py:
#   ./build.sh --style heatmap --out docs/heatmap-light.png
#   ./build.sh --column commits --theme dark --out docs/commits.png
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
[[ -x "$PY" ]] || { echo "no venv; run ./setup.sh first" >&2; exit 1; }

if [[ ! -f data/contributions.csv ]]; then
  echo "data/contributions.csv is missing -- run ./fetch.sh first" >&2
  exit 1
fi

# --dpi 55 lands each PNG at ~475px, twice the 230px the README displays them
# at, so they stay crisp on retina without committing six large binaries.
DPI=55

if (( $# )); then
  exec "$PY" spiral.py --out docs/spiral.png --dpi "$DPI" "$@"
fi

for style in dots heatmap horizon; do
  for theme in light dark; do
    "$PY" spiral.py --style "$style" --theme "$theme" --dpi "$DPI" \
          --out "docs/$style-$theme.png"
  done
done

echo
ls -1 docs/*.png docs/*.svg
