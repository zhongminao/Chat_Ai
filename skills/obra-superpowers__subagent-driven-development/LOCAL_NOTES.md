# 本地接入说明（未修改上游文件）

- `SKILL.md`、`implementer-prompt.md`、`task-reviewer-prompt.md`、`re-review-prompt.md`、`references/`、`scripts/`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- **子代理工具不存在**：上游核心是“每个任务派发一个新 implementer 子代理 + 任务审查 + 最终整支审查”。本环境只能产出**逐任务的执行 brief、任务审查清单、ledger 模板与最终复审清单**，由用户在自己的多 agent 环境中派发执行。
- **脚本未运行**：`scripts/sdd-workspace`、`scripts/task-brief`、`scripts/review-package`、`scripts/sdd-repo`（bash）**未执行、未验证**，且未授予 bash；需要这些脚本产出的工作区/brief/审查包时，按 `references/` 中的格式**手工推导**并注明“未使用上游脚本”。
- 不写盘：ledger 与审查包只在回复中给出。
- 上游自述“不中途向人工确认、自行裁决”，与本次任务的安全边界相冲突——**本接入以安全边界为准**：不可逆/破坏性操作、安全敏感操作、工作区外副作用（merge/push/发布）必须停下询问用户。
- 与 `obra-superpowers__dispatching-parallel-agents`（仅判定独立域并派发，彼此并行）、`obra-superpowers__executing-plans`（无子代理时的串行执行）、`obra-superpowers__writing-plans`（写计划）区分。
