#!/usr/bin/env bash
# Fetch the contribution history, then render it to docs/spiral.png -- the
# image the README embeds, so regenerating here updates the README too.
set -euo pipefail
cd "$(dirname "$0")"

# Pick up a local .env if present (gitignored). GITHUB_PAT is accepted as an
# alias so an existing token file doesn't need renaming.
if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi
: "${GITHUB_TOKEN:=${GITHUB_PAT:-}}"
export GITHUB_TOKEN

if [[ -z "$GITHUB_TOKEN" ]]; then
  echo "GITHUB_TOKEN is not set -- see README.md" >&2
  exit 1
fi

PY=.venv/bin/python
[[ -x "$PY" ]] || { echo "no venv; run the setup step in README.md" >&2; exit 1; }

"$PY" fetch_contributions.py "$@"
"$PY" spiral.py --column contributions --theme light --out docs/spiral.png

echo
ls -1 docs/
