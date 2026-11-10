# 本地接入说明（未修改上游文件）

- `SKILL.md`、`assets/verification-report-template.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`，**不联网**：上游第 2 层“来源核查”依赖网页搜索；本环境无法检索时，必须把相关声明标为 `PLAUSIBLE` 并说明“未检索”，**不得编造 URL 或引用**。
- 上游“active mode”（持续为每条回答附加 Verification 段）需要用户显式开启；开启后仍遵守“无来源不臆造”规则，并在结尾提示可要 full report。
- 输出以对话文本给出；未授予 `write_file`。
- 与 `obra-superpowers__verification-before-completion`（执行命令取证的完成门槛）区分：本技能核查**文本事实与引用**。
