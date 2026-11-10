# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：上游要求保存到 `/docs/ways-of-work/plan/{epic-name}/epic.md`，本环境未授予 `write_file`，PRD 内容请在对话中输出，由用户决定是否落盘。
- 与同源技能分工：
  - `github-awesome-copilot__prd`（已装）：独立产品 PRD（无需上层 Epic 上下文），本技能是**Epic 级 PRD**，产物供后续架构设计与功能拆解使用。
  - `github-awesome-copilot__breakdown-feature-prd`（已装）：从已有 Epic 拆出单个功能级 PRD；本技能管 Epic 本身。
- 后续环节 `breakdown-plan`（项目计划）与 `breakdown-test`（测试计划）是独立技能，本技能只负责 Epic PRD。
