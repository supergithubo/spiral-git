#!/usr/bin/env bash
# Render data/contributions.csv to docs/spiral.png -- the image the README
# embeds, so rebuilding here updates the README too.
#
# No network and no token: re-run this as often as you like while tuning.
# Extra flags pass through and override the defaults below, e.g.
#   ./build.sh --theme dark
#   ./build.sh --column commits --out docs/commits.png
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
[[ -x "$PY" ]] || { echo "no venv; run ./setup.sh first" >&2; exit 1; }

if [[ ! -f data/contributions.csv ]]; then
  echo "data/contributions.csv is missing -- run ./fetch.sh first" >&2
  exit 1
fi

exec "$PY" spiral.py --out docs/spiral.png "$@"
