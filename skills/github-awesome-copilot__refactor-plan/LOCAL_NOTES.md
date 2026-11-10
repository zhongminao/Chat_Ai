# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 上游要求先检索代码库（`read_file` 可用），并明确“制定计划阶段不得编辑文件”；本 manifest 只给 `read_file`，因此计划产出为对话中的 Markdown，不会改动仓库。
- 计划中的验证命令（如 `npm test`）仅作为建议写入步骤，本地不执行，也未授予 `run_bash`；执行需用户另行确认。
- 上游要求输出计划后询问“Shall I proceed with Phase 1?”并等待确认：本环境同样必须停下等待用户确认，不得自动实施。
- 未验证：只在 manifest 层面注册，未对任何仓库生成重构计划。
