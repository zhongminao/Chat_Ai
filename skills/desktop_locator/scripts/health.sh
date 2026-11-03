#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo 'usage: health.sh' >&2; exit 2; }
exec python3 "$(dirname -- "$0")/client.py" health
