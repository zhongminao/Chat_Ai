# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/*`、`assets/templates/*.drawio`、`scripts/*`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`：`scripts/validate-drawio.py`、`scripts/add-shape.py` **未运行、未验证**，不授予 `run_bash`；也不写 `.drawio` 文件。
- 接入后的交付：在对话中输出完整 mxGraphModel XML（可直接保存为 `.drawio`），并附用户自行运行的校验命令（`python scripts/validate-drawio.py <file.drawio>`）。模板文件可直接读取参考。
- 与同源 `drawio` 分工：本技能专注**XML 编写/模板/形状/校验**；`drawio` 专注**导出 PNG/SVG/PDF（内嵌 XML）的管线**。
- 未安装 VS Code 的 `hediet.vscode-drawio` 扩展，仅影响用户侧打开方式，不影响 XML 生成。
