# 本地服务与部署信息（初版）

## 仓库配置（不是在线状态）

- `chat_ai_test/config.yaml` 定义 `workspace: ./workspace`、`storage_dir: ./storage`；MCP 配置列出 `remote_windows: http://127.0.0.1:8767/mcp` 和 `web: http://127.0.0.1:8766/mcp`。
- AKShare 由 `skills/akshare/scripts/service.py` 按需在 Agent 本机启动，共用 Agent 的项目 Python 环境，使用自动分配的回环端口；`enable_mcp` 使用启动结果返回的地址。它不依赖固定 8768、指定名称的 Conda 环境、systemd 或宿主机到 KVM 的转发。
- `127.0.0.1` 是运行进程本机回环地址；没有证明远端服务器也能访问这些端口。配置存在不等于服务已启动；需查询实际运行状态。

## README 中的本地开发/运行示例

在项目根目录、合适 Conda 环境下，前端先在 `agent/web/frontend/` 执行 `npm ci`、`npm run build`；随后可按 README 用 `python -m uvicorn agent.web.app:app --host 127.0.0.1 --port 8764` 启动 Web，页面地址 `http://127.0.0.1:8764`。前端开发可在其目录执行 `npm run dev`，默认访问 `http://127.0.0.1:5173`，Vite 将 `/api` 转发到 `127.0.0.1:8764`。这些是项目文档示例，不代表已部署或进程当前运行。

## 未确认与后续模块

未确认 systemd、Docker、反向代理、TLS/域名、正式部署流程或代码风格偏好。取得用户确认的部署方案后单设 `references/deployment_*.md`，并更新 `SKILL.md`/`manifest.yaml` 引用；现阶段不要直接执行部署、覆盖现有服务或发布生产环境。
