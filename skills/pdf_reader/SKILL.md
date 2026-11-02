# PDF Reader Skill

This is a sidecar package returned by `search_resources`, not a system prompt. It does not execute anything automatically. Use the **absolute paths in the search result** for fixed scripts; do not reconstruct paths.

## Quick read

1. Create a unique directory under workspace `.skill-cache/pdf_reader/<run-id>/`.
2. Use `run_bash` with `<pdf_read.sh absolute path> "<input.pdf>" "<run-dir>" [auto|layout|raw|tsv]`. Read `<run-dir>/probe.txt`, `<run-dir>/read.meta` and the text path reported by `read.meta` using bounded `read_file` calls.
3. In auto mode, `pdf_probe.sh` recommends `raw` for probable two-column pages and `layout` otherwise. This is a heuristic, not a guaranteed reading order; verify headings, tables, captions and references against original pages. For mixed layouts, extract specific pages separately with `pdftotext -f/-l` if necessary. If auto reports OCR required, use `pdf_ocr.sh` as below.
4. If a page has no meaningful native text, use `<pdf_ocr.sh absolute path> "<input.pdf>" "<run-dir>/ocr.txt" "chi_sim+eng" 200` (or `eng` if Chinese data unavailable). OCR is an explicit fallback and not done silently.
5. Use `<pdf_render.sh absolute path>` only for page image inspection. Never modify the source PDF or write generated output next to it.

## Individual scripts

| Script | Purpose |
| --- | --- |
| pdf_probe.sh INPUT.pdf OUTPUT.txt | Metadata, per-page native byte counts, and conservative column recommendation |
| pdf_extract.sh INPUT.pdf OUTPUT.txt [auto\|layout\|raw\|tsv] | Native text extraction; default auto chooses recommendation, tsv outputs coordinates |
| pdf_read.sh INPUT.pdf OUTPUT_DIR [auto\|layout\|raw\|tsv] | Probe + native extract + `read.meta` |
| pdf_render.sh | Render pages as PNG |
| pdf_ocr.sh | Render pages and run Tesseract OCR |

`raw` follows PDF content-stream order and often helps with two-column papers, but does not guarantee semantic order; `layout` preserves visual position and can join adjacent columns; `tsv` includes coordinates and is not plain text. If a page contains less than 80 non-whitespace native bytes, consider OCR. `pdf_probe.sh` estimates columns using Poppler TSV geometry; its metadata `layout_mode=single|multi|unknown`, `column_count=1|2|unknown`, `has_coordinates=true|false`, `recommended_mode=layout|raw|ocr` is advisory. If a table needs coordinates, explicitly select `tsv`. Do not treat document-wide native text as proof that every page is text-native.

Report source, extraction method, source page numbers, requested answer and limitations. Complex tables/charts may need image inspection; this package does not fill forms or call hosted document services.
