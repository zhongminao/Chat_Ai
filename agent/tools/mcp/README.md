# MCP 结果与图片

`client.py` 负责连接、发现工具和调用，返回 SDK 的 `CallToolResult`。
每个服务的连接、初始化与发现合计最多等待 1 秒；失败只告警并跳过该服务工具，其他 MCP、本地工具和普通对话继续工作。
未注册工具由 ToolRouter 返回“当前工具不可用”的工具回执；历史记录保持原样，模型可以继续选择其他工具。
运行中已注册工具断开，仍由 router 返回对应工具错误。恢复连接后，新建会话或重启 Web／CLI 重新发现，不自动后台重试。
`results.py` 将文本/结构化数据和内联图片转换成现有的 `ToolResult`；`router.py` 注入会话图片存储和当前模型的视觉配置。运行时、模型消息和 Web 事件复用原有链路。

图片内容按字节解码，使用 SHA256 复用同一会话中的相同图片；单图限制、格式验证由 `ImageStore` 与转换器执行。图片出现在 `ToolResult.images` 中供界面显示；启用视觉时同时出现在 `model_images` 中，在模型请求边界转换为真实图像。非视觉模型保留界面显示和明确的文本回执，不向模型附加图片。视觉上下文的不同图片数量遵循 provider 配置。

支持 MCP `image` 内联内容，不自动下载 URL，也不访问其他主机返回的文件路径。远程 Windows 读图工具必须返回图片字节，而不是仅返回 `D:/...` 路径。

本地 Windows MCP 位于 `D:\code\IM_Opt\local_mcp`，默认监听 `127.0.0.1:8767/mcp`。端口转发完成后，在根目录 `config.yaml` 的 `mcp` 块增加服务器可达的 URL，然后重启 `chat_ai` 并开启新会话。未建立转发前不修改生产 MCP 配置。

验证：

```bash
python -m unittest discover -s tests -p 'test_mcp_images.py' -v
# 同时检查现有搜索 MCP（需要 127.0.0.1:8766 正常运行）：
CHAT_AI_TEST_SEARCH=1 python -m unittest discover -s tests -p 'test_mcp_images.py' -v
```

独立 Web MCP 服务端位于 `agent/mcp_servers/web.py`，本目录只维护客户端与结果转换。
