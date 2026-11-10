# 本地使用说明（openai-skills__render-deploy）

- 需要 **Render 账号、RENDER_API_KEY 或 Render MCP/CLI**；本环境**未配置**，无网络。
- 用途限定为**方法论与文件草案**：可在回复中直接给出 render.yaml 内容（Blueprint 规范、服务类型、环境变量、健康检查）与排查步骤，但**不写盘**（无 write_file）、不调用 `list_services()`、不执行 `render` CLI、不部署。
- `allowed_tools` 仅 `read_file`。不改 `~/.cursor/mcp.json` 等 MCP 配置，不设置环境变量。
- 上游的"提权重试网络"建议在本环境**不适用**。
- 真正部署需用户自行执行。
