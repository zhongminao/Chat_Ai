# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/postmortem-template.md`、`references/fishbone-example.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`：Markdown 复盘文档在对话中输出；上游可选的 HTML/DOCX/PDF 导出需 `pandoc`/`office` 工具，**未验证**，不执行。
- 上游要求“所有内容来自用户，不得编造时间戳/指标/人名/原因”；缺失项写成 open question。
- 与 `bug-receipt`（缺陷结案回执）与 `systematic-debugging`（实时排障）区分：本技能是**事后文档化复盘**。
