# 本地使用说明（openai-skills__migrate-to-codex）

- 上游脚本 `scripts/migrate-to-codex.py` 会**创建/修改/删除** `AGENTS.md`、`.codex/`、`.agents/`、`~/.codex/`；本环境**不运行该脚本**（不给 bash/write_file），也不会改动任何 Claude 或 Codex 配置。
- 可用部分：**映射参考与迁移方案**——`references/differences.md` 的逐项对照（instructions/commands/skills/MCP/hooks/agents/plugins）、迁移顺序、哪些项必须人工复核。
- 输出方式：给出目标文件该长什么样、每一步命令与校验清单，由用户在本地执行。
- 不读取 `~/.claude`、`~/.codex` 之外的隐私内容，不联网刷新上游文档（`differences.md` 标注 "Docs last checked: 2026-04-20"，需提示用户该日期）。
