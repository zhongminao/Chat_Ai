# 本地适配说明（obra-superpowers__writing-plans）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/writing-plans`，原文原字节复制；包内无脚本。
- 仅授予 `read_file`：本技能是写作指导，不直接写盘。上游建议把计划保存到 `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`；本环境未授予 `write_file`，需要落盘时由主 agent 按用户要求另行处理，或由用户自行保存。
- 上游引用 `superpowers:using-git-worktrees`、`superpowers:executing-plans`、`superpowers:test-driven-development` 等兄弟技能；本批已装 executing-plans、test-driven-development，**未装 using-git-worktrees**，相关段落仅作知识性阅读，不要假设有隔离 worktree。
- 与 `github-awesome-copilot__create-specification` / `prd` 区分：本技能只写实现计划，不写产品需求文档。
