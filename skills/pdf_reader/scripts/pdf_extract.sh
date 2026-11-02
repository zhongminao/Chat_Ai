#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 2 && $# -le 3 ]] || { echo "usage: pdf_extract.sh INPUT.pdf OUTPUT.txt [auto|layout|raw|tsv]" >&2; exit 2; }
input=$1
output=$2
mode=${3:-auto}
[[ -f "$input" ]] || { echo "input PDF not found: $input" >&2; exit 1; }
case "$mode" in
  auto)
    probe=$(mktemp)
    trap 'rm -f -- "$probe"' EXIT
    "$(dirname -- "$0")/pdf_probe.sh" "$input" "$probe"
    mode=$(sed -n 's/^recommended_mode=//p' "$probe" | head -n 1)
    # OCR is a separate page-level workflow, never silently substitute empty native text.
    [[ "$mode" != ocr ]] || { echo "native text is insufficient; use pdf_ocr.sh" >&2; exit 1; }
    ;;
  layout|raw|tsv) ;;
  *) echo "invalid extraction mode: $mode" >&2; exit 2 ;;
esac
mkdir -p -- "$(dirname -- "$output")"
temporary=$(mktemp "$(dirname -- "$output")/.pdf-extract.XXXXXXXX")
trap 'rm -f -- "$temporary"; if [[ -n "${probe:-}" ]]; then rm -f -- "$probe"; fi' EXIT
pdftotext "-$mode" -- "$input" "$temporary"
mv -- "$temporary" "$output"
trap - EXIT
