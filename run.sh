#!/usr/bin/env bash
# Fetch fresh data, then render it -- ./fetch.sh followed by ./build.sh.
#
# Use the two scripts separately if you only want to re-render; this one always
# hits the network. Flags pass through to the fetch step.
set -euo pipefail
cd "$(dirname "$0")"

./fetch.sh "$@"
./build.sh
