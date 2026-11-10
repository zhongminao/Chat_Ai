# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- 只授予 `read_file`：上游会“直接改代码并跑测试”，本环境**不改文件、不执行测试**，仅输出**重构方案 / 批量重构建议**（含改动位置、改法、风险）。
- `.github/instructions/*.md`、`.github/copilot-instructions.md` 若不存在，按路径约定请用户提供或改为通用干净代码准则，并显式说明“未找到规范文件”。
- 与 `jeffallan-claude-skills__code-reviewer`（审查 diff/PR 并给合并结论）区分：本技能面向**全项目规范一致性重构**，不产出 PR 评审/合并结论。
- 与 `github-awesome-copilot__refactor-plan`（分阶段重构路线图文档）区分：本技能是就地批量改进建议。
