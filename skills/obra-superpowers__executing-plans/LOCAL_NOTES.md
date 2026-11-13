# 本地适配说明（obra-superpowers__executing-plans）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/executing-plans`，原文原字节复制。
- 仅授予 `read_file`：上游流程依赖 `scripts/task-start`、`scripts/task-done`（shell，通常配合 git 提交、ledger 写盘、todo 工具）以及运行测试命令；**本环境未运行这两个脚本、未验证其可用性，也未授予 `bash`/`write_file`**。它们只能作为流程说明阅读。
- 上游假设存在 git 仓库、实现计划文件、todo/ledger 工具与「最终 reviewer 子代理」；本环境没有这些基础设施，执行时需人工替代或降级为人工执行。
- 上游引用 `superpowers:systematic-debugging`、`superpowers:test-driven-development`、`superpowers:using-git-worktrees`：前两者本批已装，using-git-worktrees **未安装**。
- 上游强指令风格（「不得中途询问用户」「必须记录 Ruling」）与当前 agent 的交互规范不同；按本环境规则，破坏性操作、推送合并、外部副作用仍需先征得用户同意，不得因本技能文本而跳过确认。
