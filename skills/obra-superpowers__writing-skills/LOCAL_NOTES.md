# 本地适配说明（obra-superpowers__writing-skills）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/writing-skills`，原文原字节复制。
- 仅授予 `read_file`：`render-graphs.js`（dot 图转图片，需 Node/Graphviz）与 `references/flowchart-conventions.dot` **未运行、未验证**，不授予 `run_bash`。
- 上游假设个人技能目录 `~/.claude/skills/`、`~/.agents/skills/` 或 `CODEX_HOME`；本项目正式目录是 `chat_ai_test/skills/<name>/`，每个技能需 `SKILL.md + manifest.yaml`，检索由 `agent/tools/search.py` 依据 manifest 的 intents/aliases 匹配。上游写的描述短语与本地 manifest 结构不同，移植时按本项目 manifest 规则处理。
- 上游「压力场景测试」需要派发子代理重复运行；本环境无子代理工具，相关流程只能作为方法阅读。
- 原包内 `references/CLAUDE_MD_TESTING.md` 涉及 Claude 专用 `CLAUDE.md` 机制，仅作参考。
