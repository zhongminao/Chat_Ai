# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：阅读仓库文件后，把蓝图**作为对话内容输出**（上游要求写入 `Project_Architecture_Blueprint.md`，本环境未授予 `write_file`，需用户自行保存）。
- 上游使用 Copilot 风格 `${PROJECT_TYPE=...}` 变量与 `${cond ? a : b}` 表达式，**不会自动求值**；请按用户显式回答（技术栈/模式/图表类型）挑选模板段落，缺省时用“Auto-detect”语义自行判断。
- 与 `jeffallan-claude-skills__architecture-designer` 分工：本技能是**已有代码 → 描述性蓝图**；对方是**新系统/架构方案设计**。
- 生成的架构图仅为文本/说明，不调用绘图工具。
