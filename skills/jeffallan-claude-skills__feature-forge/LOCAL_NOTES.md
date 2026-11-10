# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：新功能需求访谈 → EARS 需求 / 验收标准 / 实施清单。纯指导性技能，只授予 `read_file`。
- Claude 平台依赖（未适配）：上游要求使用 `AskUserQuestions` 工具做结构化提问，以及用 Task 子代理做预研；本平台无同名工具，按普通提问与人工沟通替代，`references/pre-discovery-subagents.md` 中的子代理流程不适用。
- 上游要求把规格保存到 `specs/{feature_name}.spec.md`；本地未授予 `write_file`，产出内容由调用方决定落盘位置。
- 未验证：未实际发起过需求访谈。
