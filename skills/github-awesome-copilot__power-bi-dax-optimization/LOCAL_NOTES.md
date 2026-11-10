# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：不连接 Power BI / Fabric，不运行 DAX 查询，性能结论基于公式结构与常见模式推断，需用户在 Power BI 里实测（DAX Studio / 性能分析器）。
- 与同源 `power-bi-model-design-review`（表/关系/星型模型）和 `power-bi-report-design-consultation`（页面视觉设计）区分：本技能只看**单个 DAX 公式的写法与性能**。
