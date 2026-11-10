# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- **所有 git / 测试命令都不执行**：上游会运行 `git rev-parse`、`git merge`、`git push -u origin`、`git worktree remove`、`git branch -d/-D` 及全量测试。本环境**不授予 run_bash**，只输出：
  - 三步菜单（合并到基线 / 推分支并开 PR / 保持原样），以及 detached HEAD 时的两项菜单；
  - 由用户**自行执行**的命令文本、执行顺序与失败处理（合并结果测试失败则停下、保留分支与 worktree）；
  - 清理清单（仅清理 `.worktrees/`、`worktrees/` 下的 worktree，其它归宿主环境）。
- 破坏性操作被严格限制：**永远不会建议 `--force` 或 `git branch -D` 作为默认路径**；丢弃工作只在用户明确要求并已确认的情况下作为文本步骤给出。
- 与 `obra-superpowers__using-git-worktrees`（开工前建隔离工作区）、`conventional-commit` / `git-commit`（写提交信息）、`code-reviewer`（审查）区分。
