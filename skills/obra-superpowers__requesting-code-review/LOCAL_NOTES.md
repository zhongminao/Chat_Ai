# 本地适配说明（obra-superpowers__requesting-code-review）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/requesting-code-review`，原文原字节复制。
- 仅授予 `read_file`：本技能核心是「准备审查请求并派发给 reviewer 子代理」。本环境没有子代理派发工具，`git rev-parse` 等命令也未授予 `bash`；`code-reviewer.md` 提示模板可按文档阅读，由主 agent 或用户手工填充后在当前会话内审查。
- 与已装 `jeffallan-claude-skills__code-reviewer` 区分：code-reviewer 是「**执行**审查」的技能；本技能是「**发起/组织**审查请求」的技能（何时审、给评审者哪些上下文、如何处理发现）。要直接审查一个 diff，用 code-reviewer。
- 上游引用 `superpowers:subagent-driven-development`（**未安装**）。
