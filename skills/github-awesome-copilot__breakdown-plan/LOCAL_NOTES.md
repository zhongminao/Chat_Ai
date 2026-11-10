# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：上游会调用 `gh` / GitHub MCP 真正创建 issue、建 project、打标签，**本环境不执行任何 GitHub 写操作**；只输出 issue 模板文本、标签方案与依赖图，由用户自行创建。
- 上游输出路径 `/docs/ways-of-work/plan/...` 不写入；内容在对话中给出。
- 与同源技能分工：`breakdown-epic-pm`（Epic PRD）→ 本技能（项目计划/issue 拆分）→ `breakdown-test`（测试计划）。
- 与 `create-implementation-plan`（已装）区分：后者是代码级实现步骤计划，本技能是项目管理层级的 issue 拆分。
