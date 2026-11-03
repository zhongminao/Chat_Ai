#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo 'usage: locate.sh < request.json' >&2; exit 2; }
exec python3 "$(dirname -- "$0")/client.py" locate
