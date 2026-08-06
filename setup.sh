#!/usr/bin/env bash
# Create the virtualenv and install dependencies.
#
# uv rather than `python -m venv` because Ubuntu ships 3.12 without ensurepip.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null; then
  echo "uv not found. Install it from https://docs.astral.sh/uv/ or, to use" >&2
  echo "the stdlib instead: sudo apt install python3.12-venv" >&2
  exit 1
fi

uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python matplotlib requests

echo
echo "Ready. Next: put a token in .env, then ./fetch.sh && ./build.sh"
