# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：上游用 `#tool:fetch` 抓取文档 URL，本环境**不联网**，请用户粘贴文档/`--help` 文本或提供本地文件；tldr 页面文本在对话中输出，不写入文件。
- 必须同时有命令名与权威文档 URL（或等价文本），缺一则按上游错误处理提示用户补齐；不得编造参数与示例。
- 与 `create-readme`（项目 README）区分：本技能只产出面向单个命令的 tldr 条目。
