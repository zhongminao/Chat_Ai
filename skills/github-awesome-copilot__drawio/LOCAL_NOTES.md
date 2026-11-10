# 本地接入说明（未修改上游文件）

- `SKILL.md`、`scripts/drawio-to-png.mjs`、`scripts/package.json`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`：**未安装** draw.io 桌面版 / Chromium / `puppeteer-core`，导出脚本 `drawio-to-png.mjs` 未运行、未验证；也不写 `.drawio` 文件。
- 接入后的交付：在对话中给出 `.drawio` 的 mxGraphModel XML，以及用户自行执行的导出命令（`cd scripts && npm install`；`node scripts/drawio-to-png.mjs <in.drawio> [out.png]`；或 `drawio -x -f png -e -b 10 -o out.png in.drawio`）。
- 与同源 `draw-io-diagram-generator` 分工：本技能专注**导出管线**（CLI/无头浏览器、PNG/SVG/PDF 内嵌 XML）；`draw-io-diagram-generator` 专注**XML 编写与校验**（模板、形状库、多页、validate 脚本）。
