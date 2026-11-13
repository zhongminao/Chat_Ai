# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/publication.md`、`scripts/*`、`tests/*`、`assets/example.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- **未安装依赖、未运行脚本**：需要 Python 包（`scripts/requirements.txt`）、Node `@mermaid-js/mermaid-cli` 与本地浏览器；`markdown_to_word.py` 与 `tests/` 均未执行，不授予 `bash`。
- 接入后的交付：给出所需命令（`python -m pip install -r scripts/requirements.txt`、`npm install --prefix ./run/mermaid-cli @mermaid-js/mermaid-cli`、`python scripts/markdown_to_word.py in.md --output out.docx --mermaid-cli ...`）与注意点（不覆盖已有 docx、不静默修复无效 mermaid、图不是可编辑 Office 形状），由用户自行执行。
- 与已有转换技能分工（避免互抢）：
  - `markdown_to_docx`（已装）：**一般** Markdown → Word（本地 PNG 图片等）；本技能只在**含 Mermaid 代码块、需要 SVG 矢量与分页处理**时使用，且不含 mermaid 时优先用 `markdown_to_docx`。
  - `office_docx`：新建/编辑 Word；`convert_word_to_md`：Word → Markdown（反向，不做）。
