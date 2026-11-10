# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/setup.md`、`scripts/*`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- **未安装依赖、未运行脚本**：`scripts/convert_excel_to_md.py` 依赖 `markitdown[xlsx]`（pandas + openpyxl），按要求不装依赖、不在本机执行，不授予 `run_bash`。
- 接入后的行为：读 `SKILL.md` 与 `references/setup.md`，向用户说明所需包与命令（`python -m pip install -r scripts/requirements.txt`，`python scripts/convert_excel_to_md.py <file.xlsx>`），由用户自行安装并执行；或在用户已提供表格内容时直接整理成 Markdown 表格。
- 仅支持 `.xlsx`；`.xls` 需先另存为 `.xlsx`。脚本默认在源文件旁生成 `<name>/<name>.md` 与 `img/`（会写盘），需用户自己在终端运行并确认输出路径。
- 与已有技能分工（避免互抢）：本技能**只做 xlsx → markdown**；PDF 读取用 `pdf_reader`；Word → markdown 用 `convert_word_to_md`；生成/编辑 Excel 用 `office_xlsx`。
- 同源兄弟技能 `convert-pdf-to-md`、`convert-plaintext-to-md` 另行接入，各自只看自己的格式。
