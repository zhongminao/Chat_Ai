# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/setup.md`、`scripts/*`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- **未安装依赖、未运行脚本**：`scripts/convert_pdf_to_md.py` 依赖 `markitdown[pdf]` + `pymupdf`，按要求不装依赖、不执行，不授予 `bash`。
- 接入后的行为：说明所需依赖与命令（`python -m pip install -r scripts/requirements.txt`，`python scripts/convert_pdf_to_md.py <file.pdf>`），由用户执行；输出 `<name>/<name>.md` 与 `img/`（默认写在源文件旁，会写盘，需用户确认）。
- 与已有技能分工（避免互抢）：
  - `pdf_reader`（已装）：**直接读取** PDF 文本/渲染 OCR；本技能是其中“转成 Markdown 文件并导出图片”的专项流程，需要提取表格与图片、或要留档 markdown 时用。
  - `convert_word_to_md`：Word → markdown；`office_xlsx`：Excel 编辑；`markdown_to_docx`：markdown → Word。
- 只支持 `.pdf`；不做 markdown → pdf 反向转换。
