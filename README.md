# chat_ai

## 开发约定

代码保持简洁，模块职责清晰，功能通过小模块组合。CLI、Web 和核心控制器共用事件流；界面逻辑不进入核心。文档只记录真实行为和必要入口。

## 当前结构

```text
agent/core/       Controller、状态转移和工具调度
agent/model/      模型协议、provider、模型目录
agent/tools/      本地工具、schema、router、spill
agent/tools/mcp/  MCP 客户端与 adapter
agent/storage/    session 和 events.jsonl
agent/workflow/   配置、AgentState、HistoryNode、命令
agent/cli/        CLI
agent/web/        FastAPI、SSE、页面
config.yaml       项目配置
```

## 运行

```bash
cd ~/mydisk/tools/chat_ai
conda activate py313
pip install -e .
python -m agent.cli.main
```

继续会话：

```bash
python -m agent.cli.main --session <session_id>
```

启动 Web：

```bash
uvicorn agent.web.app:app --host 127.0.0.1 --port 8764
```

Web 前端使用 React + TypeScript + Vite，源码位于 `agent/web/frontend/`。
首次启动 Web 前先构建前端（需要 Node.js 20.19+ 或 22.12+）：

```bash
cd agent/web/frontend
npm ci
npm run build
```

生产访问 `http://127.0.0.1:8764`；FastAPI 提供 `dist/index.html`、`/assets` 和原有 `/api`。
8764 是网页服务端口，模型仍由 provider 配置选择，可直接使用 DeepSeek API。

前端开发时保持上述 FastAPI 服务运行，在另一个终端执行：

```bash
cd /home/zhong/mydisk/tools/chat_ai/agent/web/frontend
npm run dev
```

访问 `http://127.0.0.1:5173`，Vite 将 `/api` 代理到 `127.0.0.1:8764`。
前端检查：`npm test`；`npm run build` 包含 TypeScript 检查。

前端按职责组织：`features/` 包含会话、对话和模型选择，`api/` 封装原有 HTTP/SSE，
`state/` 统一处理历史事件回放与实时事件，`styles.css` 管理样式。
消息内容暂时按纯文本展示，格式扩展入口是 `MessageContent.tsx`。
事件订阅使用现有 `after`/`Last-Event-ID` 协议，切换会话会关闭旧连接；首屏从现有事件流回放历史。
CLI、Controller、业务 API 和事件格式保持原有行为。

模型 API 密钥由 provider 配置指定的环境变量提供。

## 状态与运行时
`agent/core/control.py` 提供运行控制状态。Web 和 CLI 共用 `ControlState`；当前支持停止正在执行的 turn，控制信号不写入 `AgentState`。Web 通过
`POST /api/sessions/{session_id}/control/stop` 请求停止，CLI 使用 `Ctrl+C`。


`state` 只保存可记录、可回放、可传输的 JSON 数据。`runtime` 保存连接、客户端、线程和回调。MCP 的名称、URL、工具 schema 进入 state；MCP 连接和工具映射留在 runtime。核心只使用统一工具列表和调用接口。

`events.jsonl` 是程序唯一事件流。`HistoryNode` 从事件流恢复消息，CLI 和 Web 使用同一套恢复流程。工具输出过大时写入工作目录 `.spill/<session_id>/`，模型通过 `read_file` 读取。

## MCP 与网页工具

`config.yaml` 中配置 MCP URL：

```yaml
mcp:
  search: http://127.0.0.1:8766/mcp
```

`agent/tools/mcp/adapter/web_mcp.py` 提供：

- `search`：调用本地 SearXNG 搜索网页
- `fetch_url`：读取公开网页的静态 HTML 文本

SearXNG 是搜索后端；`web_mcp.py` 是 MCP 适配层。`fetch_url` 不执行 JavaScript，也不提供登录和浏览器操作。

## 下一阶段：混合检索

目标是组合关键词检索和向量检索：

```text
查询
→ 关键词召回
→ 向量召回
→ 合并、去重、排序
→ 返回统一结果
```

先保持检索模块独立，不把索引、向量库和排序逻辑放进 `Controller`。具体数据源、向量模型和存储方式在实现前单独确定。
