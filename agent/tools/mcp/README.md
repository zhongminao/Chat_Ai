# MCP 结果与图片

`client.py` 负责连接、发现工具和调用，返回 SDK 的 `CallToolResult`。
`results.py` 将文本/结构化数据和内联图片转换成现有的 `ToolResult`；`router.py` 注入会话图片存储和当前模型的视觉配置。控制器、模型消息和 Web 事件复用原有链路。

图片内容按字节解码，使用 SHA256 复用同一会话中的相同图片；单图限制、格式验证由 `ImageStore` 与转换器执行。图片出现在 `ToolResult.images` 中供界面显示；启用视觉时同时出现在 `model_images` 中，在模型请求边界转换为真实图像。非视觉模型保留界面显示和明确的文本回执，不向模型附加图片。视觉上下文的不同图片数量遵循 provider 配置。

支持 MCP `image` 内联内容，不自动下载 URL，也不访问其他主机返回的文件路径。远程 Windows 读图工具必须返回图片字节，而不是仅返回 `D:/...` 路径。

本地 Windows MCP 位于 `D:\code\IM_Opt\local_mcp`，默认监听 `127.0.0.1:8767/mcp`。端口转发完成后，在根目录 `config.yaml` 的 `mcp` 块增加服务器可达的 URL，然后重启 `chat_ai` 并开启新会话。未建立转发前不修改生产 MCP 配置。

验证：

```bash
python -m unittest discover -s tests -p 'test_mcp_images.py' -v
# 同时检查现有搜索 MCP（需要 127.0.0.1:8766 正常运行）：
CHAT_AI_TEST_SEARCH=1 python -m unittest discover -s tests -p 'test_mcp_images.py' -v
```
