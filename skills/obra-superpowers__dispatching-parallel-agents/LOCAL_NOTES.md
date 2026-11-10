# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- **本环境没有子代理派发工具**：上游的 `Subagent (...)` 派发步骤无法执行。本技能只负责**判定独立性 + 产出可直接粘贴的派发提示词**（每个问题域一份：范围、目标、约束、期望输出），由用户在自己的 agent 环境里派发。
- 只授予 `read_file`：不跑测试、不改代码；上游“派发后跑全量测试并核对冲突”改为**给出人工核查清单**。
- 与 `obra-superpowers__subagent-driven-development`（带 implementer/re-reviewer 提示与脚本的一对一子代理开发全流程）区分：本技能只做**拆分与派发提示**；与 `obra-superpowers__diagnosing-superpowers`（会话复盘）区分。
