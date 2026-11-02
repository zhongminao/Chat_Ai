#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 2 && $# -le 3 ]] || { echo "usage: pdf_render.sh INPUT.pdf OUTPUT_DIR [DPI]" >&2; exit 2; }
input=$1
output_dir=$2
dpi=200
[ $# -ge 3 ] && dpi=$3
[[ -f "$input" ]] || { echo "input PDF not found: $input" >&2; exit 1; }
[[ "$dpi" =~ ^[0-9]+$ && "$dpi" -ge 72 && "$dpi" -le 600 ]] || { echo "DPI must be 72..600" >&2; exit 2; }
mkdir -p -- "$output_dir"
pdftoppm -png -r "$dpi" -- "$input" "$output_dir/page"
