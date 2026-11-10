# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/*`、`templates/*.excalidraw`、`scripts/*`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`：`scripts/add-arrow.py`、`add-icon-to-diagram.py`、`split-excalidraw-library.py` **未运行、未验证**，不授予 `run_bash`；不写 `.excalidraw` 文件。
- 交付方式：在对话中给出完整 `.excalidraw` JSON（可保存后用 excalidraw.com 打开），并说明需要的 id/binding 约定；模板文件可读取参考。
- 与 `draw-io-diagram-generator` / `drawio`（.drawio 格式）区分：本技能只产出 Excalidraw 格式。
