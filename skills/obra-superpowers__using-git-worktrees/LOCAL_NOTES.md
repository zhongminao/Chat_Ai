# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- **所有 git / 安装命令都不执行**：上游要求运行 `git rev-parse`、`git check-ignore`、`git worktree add`、`npm install`/`pip install -r requirements.txt` 等。本环境**不授予 bash，也不装依赖**，只输出：
  - 判定流程（先检测是否已在 linked worktree / 子模块，再选目录，再确认目录被忽略）；
  - 逐条可复制的命令文本及其作用、失败时的处理（含沙箱权限失败时原地工作）；
  - 基线测试建议（由用户执行）。
- 不修改 `.gitignore`、不写入任何文件；需要添加忽略项时只给出建议 diff。
- 与 `obra-superpowers__finishing-a-development-branch`（收尾：合并/PR/清理）区分：本技能只负责**开工前创建隔离工作区**。
