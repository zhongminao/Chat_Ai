#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 2 && $# -le 3 ]] || { echo "usage: pdf_read.sh INPUT.pdf OUTPUT_DIR [auto|layout|raw|tsv]" >&2; exit 2; }
input=$1
output_dir=$2
mode=${3:-auto}
[[ -f "$input" ]] || { echo "input PDF not found: $input" >&2; exit 1; }
case "$mode" in auto|layout|raw|tsv) ;; *) echo "invalid mode: $mode" >&2; exit 2 ;; esac
mkdir -p -- "$output_dir"
script_dir=$(dirname -- "$0")
"$script_dir/pdf_probe.sh" "$input" "$output_dir/probe.txt"
if [[ "$mode" == auto ]]; then
  mode=$(sed -n 's/^recommended_mode=//p' "$output_dir/probe.txt" | head -n 1)
fi
if [[ "$mode" == ocr ]]; then
  echo "Native text is insufficient; run pdf_ocr.sh for weak pages." >&2
  exit 1
fi
"$script_dir/pdf_extract.sh" "$input" "$output_dir/text.$([[ "$mode" == tsv ]] && echo tsv || echo txt)" "$mode"
printf 'source=%s\nmode=%s\nprobe=%s\ntext=%s\n' "$input" "$mode" "$output_dir/probe.txt" "$output_dir/text.$([[ "$mode" == tsv ]] && echo tsv || echo txt)" > "$output_dir/read.meta"
cat -- "$output_dir/read.meta"
