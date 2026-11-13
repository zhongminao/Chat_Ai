---
name: akshare
description: 查询股票和 ETF 的行情、行业、资金流、财务及公开持仓，也可批量采集财经数据。
---

# AKShare 财经数据

## 第一步：启动服务

调用 `bash`，将下面命令原样作为 `command`：

```bash
{{python}} {{skill_dir}}/scripts/service.py start
```

使用 Agent 自身的 Python 环境；命令中的路径已由检索工具填好。启动只检查依赖和启动进程，不安装软件、不创建环境。

返回 JSON 中 `running: true` 才继续第二步。返回 `state: failed` 时，根据 `error` 报告原因，停止重试；缺少依赖应在部署时统一安装项目 `requirements.txt`。

## 第二步：连接 MCP

调用 `enable_mcp`，把第一步返回的 `url` 原样作为 `url` 参数。下一轮工具列表会出现该 MCP 的三个工具，使用列表中的实际工具名。

## 第三步：查询数据

依次使用以下三个 MCP 工具：

1. `search_interfaces`：搜索用户需要的财经接口。例如查股票报价用 `{"keyword":"个股 实时"}`，查 ETF 报价用 `{"keyword":"ETF 实时"}`。
2. `describe_interface`：把搜索结果中的接口名作为 `name`，确认参数及证券类型。
3. `get_data`：传 `name`、`params`、`max_rows`，例如先取 `max_rows: 5`。按说明传股票代码、日期等参数。

先确认证券名称及类型，ETF 使用基金类接口。查询今日行情须核对数据时间、最新价、涨跌幅、成交量或成交额；历史收盘价不能当作实时价。结果注明来源和数据时间，缺失字段明确说明。源站失败时可检索其他来源并说明切换，不循环重试同一失败接口。

## 运行方式

- 保留原版 AKTools 全部接口、HTTP API 和 MCP，无额外接口白名单。
- Agent 和 Skill 共用当前主机的项目环境，不要求 Conda 环境叫什么。项目使用 64 位 Python 3.11+，部署时统一安装依赖。
- 服务只监听 Agent 本机 `127.0.0.1`，端口由启动结果返回；无需 root、宿主机转发或固定 MCP 配置。
- 空闲 15 分钟自动退出；查询结束不用停止。地址失效时从第一步重新启动。
- 查询状态：`{{python}} {{skill_dir}}/scripts/service.py status`。
- 手动停止：`{{python}} {{skill_dir}}/scripts/service.py stop`。
- HTTP 文档地址为返回地址去掉 `/mcp` 后加 `/docs`。批量采集可用 Python 或 HTTP API，调度和存储另行安排。
- 股东披露有滞后，ETF 份额变化不能直接确认买方身份。
