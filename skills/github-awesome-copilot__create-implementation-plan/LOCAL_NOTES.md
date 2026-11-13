# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 与 PRD 系列区分：本技能只产出**实施计划**（阶段、TASK 表、验证标准），不写需求/规格文档（`prd`、`create-specification`、`breakdown-feature-prd` 仍负责那一侧）。
- 上游提示变量 `${input:PlanPurpose}` 不解析，按用户描述替换；输出目录 `/plan/` 在本环境视为项目内 `plan/`。
- 写盘：上游要求创建 `/plan/[purpose]-[component]-[version].md`。本 manifest **未授予** `write_file`，计划以对话输出，落盘由调用方确认。
- 标识符唯一性检查依赖 shell 的 `grep/sed/sort/uniq`；本技能未授予 `bash`，需人工核对 TASK/GOAL 等编号是否重复声明。
- 未验证：只在 manifest 层面注册，未生成计划文件。
