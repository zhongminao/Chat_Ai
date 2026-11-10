# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 写盘：上游 Step 3 要求在仓库根创建 `llms.txt`。本 manifest **未授予** `write_file`，因此只输出可直接保存的 `llms.txt` 内容；写入需调用方确认路径。
- 联网：上游要求先阅读 https://llmstxt.org/ 规范。本地不联网，按 `SKILL.md` 内嵌的格式要求生成；若规范已变更，以 SKILL.md 描述的版本为准。
- 链接必须使用仓库内真实存在的相对路径（可用 `read_file` 核对），不得编造。
- 与 `update-llms`（更新已有 llms.txt）区分：本技能面向从零创建。
- 未验证：只在 manifest 层面注册，未在真实仓库生成 llms.txt。
