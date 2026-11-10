# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 上游 front matter 声明 `allowed-tools: shell(git:*)`，工作流会真实执行 `git status` / `git diff` / `git add` / `git commit`。本 manifest **只授予 `read_file`**，所以接入后只能：
  1. 读仓库内文件（如 `CONTRIBUTING.md`、`commitlint.config.js`）推断提交规则；
  2. 根据用户粘贴的 `git status` / `git diff` 内容给出**建议的**暂存与提交命令序列和消息文本。
- **不要**自动执行任何 git 命令；`git add`、`git commit`、`--amend`、`--no-verify`、push 均须用户自行确认执行。
- 与 `conventional-commit` 的分工：那个技能只产出 Conventional Commits 消息文本；本技能覆盖“检查变更 → 拆分 → 暂存 → 提交”的完整流程建议。
- 未验证：只在 manifest 层面注册，未在任何仓库运行 git。
