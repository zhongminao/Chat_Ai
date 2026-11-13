# 本地接入说明（未修改上游文件）

- `SKILL.md`、`reference/`、`scripts/`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：MCP（Model Context Protocol）服务器开发指导——工具命名/描述/错误信息设计、Python FastMCP 与 Node/TypeScript SDK 实现、评测集编写。
- 脚本未运行、依赖未安装：`scripts/requirements.txt` 要求 `anthropic>=0.39.0`、`mcp>=1.1.0`，均未安装；`scripts/connections.py`、`scripts/evaluation.py` 未执行。`scripts/evaluation.py` 若运行会调用模型服务，需外部 API key（本机未配置）。
- 创建 MCP server 时需要对应语言的包管理器（npm / pip）与 MCP 客户端，本技能未获得 `bash`，无法创建工程或安装依赖。
- 未验证：未实际生成或运行任何 MCP server，检索命中不代表功能可用。
