# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：上游要求保存到 `/docs/adr/adr-NNNN-[title-slug].md` 并按序号递增，本环境**不写盘**，ADR 文本在对话中输出，编号由用户核对。
- `${input:DecisionTitle}` 等 Copilot 输入变量不会被解析；缺 Context/Decision/Alternatives/Stakeholders 时应先向用户提问。
- 与 `architecture-blueprint-generator`（描述现有架构）区分：本技能记录**单次决策**及其取舍；系统架构方案设计属 `jeffallan-claude-skills__architecture-designer`。
