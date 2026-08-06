#!/usr/bin/env bash
# Pull the contribution history from GitHub into data/contributions.csv.
#
# This is the only script that touches the network, so run it when you want
# fresh numbers -- not on every render. Extra flags pass through, e.g.
#   ./fetch.sh --since 2018
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
[[ -x "$PY" ]] || { echo "no venv; run ./setup.sh first" >&2; exit 1; }

exec "$PY" fetch_contributions.py "$@"
