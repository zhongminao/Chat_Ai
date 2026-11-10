# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯提示词技能，只授予 `read_file`：上游示例用 `cp file file.md` 原地创建副本再改写，**本环境不复制、不写盘**；转换结果直接在对话中输出为 Markdown，由用户自行保存。
- 上游的 `#tool:fetch`（抓取 Reference 链接）、`#file:`、`{{...}}` 参数语法为 Copilot 专用，不会被解析；需要哪个选项请用户直接说明（如 `--header 2`、`pre=rm-head-digits`、`-s eof`）。
- 只处理**纯文本 / .txt / 无格式文档**；PDF、Word、Excel 请用各自转换技能（`convert-pdf-to-md`、`convert_word_to_md`、`convert-excel-to-md`），markdown → html 用 `markdown-to-html`。
- 与 `documentation-writer` 分工：后者负责文档结构与 Diátaxis 分类写作，本技能只做格式排版转换。
