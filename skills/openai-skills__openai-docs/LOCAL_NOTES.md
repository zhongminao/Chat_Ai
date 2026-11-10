# 本地使用说明（openai-skills__openai-docs）

- 上游依赖 **OpenAI 开发者文档 MCP** 与网络抓取（`scripts/fetch-codex-manual.mjs`、`resolve-latest-model-info.js`）；本环境**无该 MCP、不联网、不运行 Node 脚本**。
- 因此"最新模型/最新文档"类问题只能使用包内回退资料：`references/latest-model.md`、`upgrade-guide.md`、`prompting-guide.md`（**内容可能已过时**，需明确告知用户"这是随包快照，非实时"）。
- 可用部分：**方法论**——模型升级的窄化改动原则、提示词升级优先、Codex 能力面（AGENTS.md / .codex/config.toml / skill / plugin / MCP / hook / automation）与用途的对应表、回答边界与不确定性处理。
- `allowed_tools` 仅 `read_file`：不安装 MCP、不改 `~/.codex`、不写缓存、不抓网页。
- 不要编造价格、可用性或参数；不确定时按技能要求给出"有界不确定"并建议用户查官方文档。
