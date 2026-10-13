# chat_ai 交接文档

## 开发约定

代码保持简洁，模块职责清晰，功能通过小模块组合。CLI、Web 和核心控制器共用同一套事件流；界面逻辑不进入核心。文档保持简洁，只记录当前真实行为。

## 架构边界
- **control**：`agent/core/control.py` 保存当前运行控制信号；Web 和 CLI 共用，当前支持 stop。它属于 runtime 控制状态，不写入可回放的 `AgentState`。


- **state**：可记录、可回放、可传输的 JSON；保存消息、工具 schema、MCP 名称和 URL 等数据。
- **runtime**：保存 MCP 连接、客户端、线程、回调和工具名称映射。
- **core**：使用统一工具列表和调用接口，不区分本地工具与 MCP 工具。

MCP 客户端在 `agent/tools/mcp/client.py`，适配器在 `agent/tools/mcp/adapter/`，工具由 `agent/tools/router.py` 统一路由。

## 当前入口

```bash
cd /home/zhong/mydisk/tools/chat_ai
conda activate py313
pip install -e .
python -m agent.cli.main
uvicorn agent.web.app:app --host 127.0.0.1 --port 8764
```

模型配置来自 `config.yaml` 和 `agent/model/providers/providers.yaml`。模型切换是 workflow 命令，核心接收新状态。

## 存储与历史

每个 session 位于 `storage/sessions/<session_id>/`，包含 `session.json` 和 `events.jsonl`。`events.jsonl` 是程序唯一事件流。`HistoryNode` 读取事件并返回新的 `AgentState`，CLI 和 Web 共用它。大工具输出写入工作目录 `.spill/<session_id>/`，由 `read_file` 分页读取。

## MCP 服务

`config.yaml` 当前配置：

```yaml
mcp:
  search: http://127.0.0.1:8766/mcp
```

`agent/tools/mcp/adapter/web_mcp.py` 是网页 MCP 适配器：`search` 调用 SearXNG，`fetch_url` 使用 HTTP 读取静态 HTML。它由 `systemd --user` 的 `chat-search-mcp.service` 运行。

SearXNG 地址为 `http://127.0.0.1:8888`，只作为搜索后端，不提供 MCP 接口。

## 下一阶段任务：混合检索

实现关键词检索 + 向量检索的统一检索模块，流程为：

```text
query → keyword retriever + vector retriever → merge/deduplicate/rank → results
```

要求：

1. 检索器独立于 `Controller`。
2. 先定义统一的 JSON 结果结构。
3. 关键词检索和向量检索可单独测试。
4. 合并、去重、排序保持为独立小模块。
5. 完成前先确定被检索对象、向量模型和索引存储方式。
