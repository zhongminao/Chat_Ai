# 本地使用说明（openai-skills__chatgpt-apps）

- 上游要求**先查最新官方文档**（`$openai-docs` 或 OpenAI 文档 MCP，逐个 fetch apps-sdk 页面）。本环境**无网络、无该 MCP**，因此：
  - 不得声称已核对最新 Apps SDK 文档；只依据包内 `references/` 与 SKILL.md 的通用模式作答。
  - 需要版本细节时，明确告知用户"请以 developers.openai.com Apps SDK 当前文档为准"。
- `scripts/scaffold_node_ext_apps.mjs`（Node 脚手架）**未运行、未安装依赖**；`allowed_tools` 仅 `read_file`，不执行脚本、不写盘、不部署、不上架。
- 不发起任何 ChatGPT 提交/联网操作；如涉及上架，只输出清单与方案。
- 与已装 `anthropics-skills__mcp-builder` 的区别：后者面向 MCP 服务端构建（Claude 生态），本技能面向 ChatGPT Apps SDK（widget/桥接/上架）。
