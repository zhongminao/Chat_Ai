# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 上游流程会运行 `git status` / `git diff` 并**自动创建并切换分支**；本 manifest 只授予 `read_file`，因此：
  1. 依赖用户粘贴的 `git status` / `git diff` 或已知改动说明进行分类；
  2. 只输出**建议的分支名**与 `git checkout -b ...` 命令文本，不执行任何 git 命令。
- 与 `git-commit`（提交消息与暂存）和 `conventional-commit`（提交消息格式）区分：本技能只管**分支类型与命名**。
