#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 2 && $# -le 4 ]] || { echo "usage: pdf_ocr.sh INPUT.pdf OUTPUT.txt [LANG] [DPI]" >&2; exit 2; }
input=$1
output=$2
lang=eng
[ $# -ge 3 ] && lang=$3
dpi=200
[ $# -ge 4 ] && dpi=$4
[[ -f "$input" ]] || { echo "input PDF not found: $input" >&2; exit 1; }
[[ "$dpi" =~ ^[0-9]+$ && "$dpi" -ge 72 && "$dpi" -le 600 ]] || { echo "DPI must be 72..600" >&2; exit 2; }
mkdir -p -- "$(dirname -- "$output")"
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT
pdfinfo -- "$input" > "$work_dir/pdfinfo.txt"
pages=$(awk -F: '/^Pages:/ {gsub(/[[:space:]]/, "", $2); print $2}' "$work_dir/pdfinfo.txt")
[ -n "$pages" ] || pages=0
pdftoppm -png -r "$dpi" -- "$input" "$work_dir/page"
temporary=$(mktemp)
trap 'rm -f -- "$temporary"; rm -rf -- "$work_dir"' EXIT
: > "$temporary"
for page in $(seq 1 "$pages"); do
  image="$work_dir/page-$page.png"
  [[ -f "$image" ]] || { echo "rendered page missing: $page" >&2; exit 1; }
  printf '\f--- page %s ---\n' "$page" >> "$temporary"
  tesseract "$image" stdout -l "$lang" --psm 3 >> "$temporary"
  printf '\n' >> "$temporary"
done
mv -- "$temporary" "$output"
trap - EXIT
