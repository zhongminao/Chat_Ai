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
