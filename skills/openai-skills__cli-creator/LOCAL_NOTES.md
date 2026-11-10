# 本地使用说明（openai-skills__cli-creator）

- 纯方法论型：可离线直接作为指导使用（命令面设计、JSON 契约、认证优先级、冒烟测试清单）。
- `allowed_tools` 仅 `read_file`：**不执行** `cargo`/`pnpm`/`pip` 安装、不写 `~/code/clis`、不改 PATH、不运行 `command -v` 之外的任何探测命令。
- 生成 CLI 代码需另行授权 write_file；本环境下只输出**代码与步骤建议**，由用户自行落地。
- 不联网（不下载 OpenAPI/SDK）；若需要规范原文，请用户提供文件。
- 与已装 `jeffallan-claude-skills__cli-developer` 的区别：后者关注既有 CLI 程序的实现与交互；本技能关注**从 API/OpenAPI 规划全新 CLI 的命令面与契约**。
