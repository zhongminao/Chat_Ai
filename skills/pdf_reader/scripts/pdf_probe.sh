#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 2 ]] || { echo "usage: pdf_probe.sh INPUT.pdf OUTPUT.txt" >&2; exit 2; }
input=$1
output=$2
[[ -f "$input" ]] || { echo "input PDF not found: $input" >&2; exit 1; }
mkdir -p -- "$(dirname -- "$output")"
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT
pdfinfo -- "$input" > "$work_dir/pdfinfo.txt"
pdftotext -layout -- "$input" "$work_dir/all.txt"
pages=$(awk -F: '/^Pages:/ {gsub(/[[:space:]]/, "", $2); print $2}' "$work_dir/pdfinfo.txt")
[ -n "$pages" ] || pages=0
encrypted=$(awk -F: '/^Encrypted:/ {gsub(/^[[:space:]]+/, "", $2); print $2}' "$work_dir/pdfinfo.txt")
[ -n "$encrypted" ] || encrypted=unknown
total_bytes=$(wc -c < "$work_dir/all.txt" | tr -d '[:space:]')
total_nonspace=$(tr -d '[:space:]' < "$work_dir/all.txt" | wc -c | tr -d '[:space:]')
{
  echo "source=$input"
  echo "pages=$pages"
  echo "encrypted=$encrypted"
  echo "native_text_bytes=$total_bytes"
  echo "native_nonspace_bytes=$total_nonspace"
  # TSV is coordinate metadata; empty or malformed data leaves layout unknown.
  pdftotext -tsv -- "$input" "$work_dir/coords.tsv"
  read -r layout_mode column_count < <(python3 "$(dirname -- "$0")/pdf_layout.py" "$work_dir/coords.tsv")
  if [[ "$total_nonspace" -lt 80 ]]; then recommended_mode=ocr
  elif [[ "$layout_mode" == multi ]]; then recommended_mode=raw
  else recommended_mode=layout; fi
  echo "layout_mode=$layout_mode"
  echo "column_count=$column_count"
  echo "has_coordinates=true"
  echo "recommended_mode=$recommended_mode"
  echo "page_bytes_begin"
  for page in $(seq 1 "$pages"); do
    page_file="$work_dir/page-$page.txt"
    pdftotext -f "$page" -l "$page" -layout -- "$input" "$page_file"
    bytes=$(wc -c < "$page_file" | tr -d '[:space:]')
    nonspace=$(tr -d '[:space:]' < "$page_file" | wc -c | tr -d '[:space:]')
    printf 'page=%s bytes=%s nonspace_bytes=%s method=native\n' "$page" "$bytes" "$nonspace"
  done
  echo "page_bytes_end"
} > "$output"
