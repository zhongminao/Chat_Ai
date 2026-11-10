# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原始文件；本文件与 `manifest.yaml` 为本地新增。
- 写盘风险：技能默认会直接创建/覆盖目标项目的 `README.md`。本 manifest 授予 `write_file` 仅用于该 README；实际写入需调用方确认，不自动批量改写已有文档。
- SKILL.md 中列出若干外部 GitHub 示例 URL 作为风格参考；不访问它们也能产出 README（不要求联网）。
- 未验证：没有在真实仓库上运行过，README 质量与措辞未做功能验证。
