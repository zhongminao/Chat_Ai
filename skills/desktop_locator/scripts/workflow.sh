#!/usr/bin/env bash
set -euo pipefail
# Python 3.10+ with Pillow. One-shot: starts service on a random loopback port and closes it.
exec python3 "$(dirname -- "$0")/workflow.py" "$@"
