# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 风险提示：上游步骤要求执行 `git add` 与 `git commit -m ...`（原文称“无需确认自动执行”）。本 manifest **未授予** `bash`，接入后仅用于生成提交信息；实际暂存/提交必须由调用方另行确认。
- 未验证：只在 manifest 层面注册，未在任何仓库执行 git 操作。
