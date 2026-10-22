# chat_ai

一个同时提供 CLI 与 Web 的 Agent 框架，支持模型与工具循环、主子 Agent、工具审批、运行中引导、图像输入和自动上下文整理。
CLI 与 Web 共用运行时、状态更新和事件协议；模型推理、MCP 服务及网络代理独立部署。

## 项目结构

```text
agent/core/       Agent 装配、会话运行时、模型与工具循环、子任务监控
agent/model/      模型目录、provider、HTTP 客户端与请求消息组装
agent/workflow/   状态类型与更新、历史恢复、上下文整理、配置
agent/tools/      本地工具、统一路由、审批、输出落盘与 MCP 客户端
agent/storage/    SQLite 会话与事件、图片元数据、附件与报告
agent/cli/        命令行交互
agent/web/        FastAPI、SSE 与 React/TypeScript 前端
prompts/         主 Agent、子 Agent、上下文整理提示词
config.yaml      CLI/Web 共用配置
```

保持代码简洁、职责清晰；简单状态操作集中管理，复杂变更单独成模块。界面逻辑不进入核心，不为拆分增加无必要的封装。

## 安装与运行

可使用 Conda Python 3.13；SQLite 必须 >= 3.51.3。前端需要 Node.js 20.19+ 或 22.12+。
在项目根目录执行：

```bash
conda create -n chat-ai-py313 python=3.13.2 'sqlite>=3.51.3' pip
conda activate chat-ai-py313
python -m pip install -e .
mkdir -p workspace
```

### Web 使用

首次启动 Web 先构建前端，再回到项目根目录启动后端：

```bash
conda activate chat-ai-py313
cd agent/web/frontend
npm ci
npm run build
cd ../../..
python -m uvicorn agent.web.app:app --host 127.0.0.1 --port 8764
```

服务正常运行时使用一次 Ctrl+C（或 SIGTERM）即可退出，即使浏览器仍保持 SSE
连接。请保留 uvicorn 默认的 lifespan（不要传 `--lifespan off`）：应用启动时会
转发并保留服务器原有信号处理，同时通知 SSE 结束，再由 uvicorn 正常排空请求。
嵌入非主线程的 ASGI 服务应由宿主负责取消长连接；若部署环境还包含可能阻塞的
第三方请求，可额外设置 `--timeout-graceful-shutdown 10` 作为退出时间上限。
退出回归测试（独立随机端口、临时配置与 storage，不访问模型）：
`python -m unittest discover -s tests -p 'test_web_shutdown.py' -v`。

访问 `http://127.0.0.1:8764`，后端同时提供构建后的页面、静态资源与 `/api`。
前端开发可在 `agent/web/frontend/` 执行 `npm run dev`，访问 `http://127.0.0.1:5173`；Vite 默认将 `/api` 转到 `127.0.0.1:8764`。
修改 Python 后端需重启进程，生产前端修改后需重新构建。

### CLI 使用

在项目根目录执行：

```bash
conda activate chat-ai-py313
python -m agent.cli.main
```

继续会话或发送一次性图文请求：

```bash
python -m agent.cli.main --session <session_id>
python -m agent.cli.main "描述图片" --image /path/to/image.png
```

## 配置

配置优先级：显式配置路径 → `CHAT_AI_CONFIG` → 项目 `config.yaml`。
相对路径以配置文件所在目录为基准；`workspace` 必须存在，文件工具与 Bash 使用该工作区。

| 配置入口 | 用途 |
| --- | --- |
| `workspace`、`storage_dir` | 工作区与会话存储目录 |
| `providers_file` | 模型目录，默认 `agent/model/providers/providers.yaml` |
| `max_rounds` | 每次用户请求或子任务的模型调用轮数上限 |
| `system_prompt_file`、`child_system_prompt_file` | `prompts/main_agent.md`、`prompts/child_agent.md` |
| `approval.mode` | 新主会话默认 `audit` 或 `full_access` |
| `context` | 自动整理开关、触发阈值和 `prompts/context_compaction.md` |
| `spill` | 长工具输出阈值与目录；`directory: .spill` 相对工作区，必须位于工作区内 |
| `mcp` | MCP 服务别名到 URL 的映射 |

提示词里的 `{workspace}` 替换为实际工作区路径。配置或提示词变更后重启 Web/CLI。
模型目录声明接口地址、模型与视觉等能力；`base_url_env` 可覆盖部署地址，`api_key_env` 可指定密钥环境变量。
`CHAT_AI_DEFAULT_PROVIDER` 只覆盖新会话默认 provider；目录展示不代表对应端点当前可用，不自动切换到其他模型。

## 主要使用规则

- **会话与停止**：每个 session 独立持有状态，同一会话串行执行，不同会话可并发。停止会取消当前执行并关闭本地请求；停止主会话不会自动停止子任务。不要用 CLI 与 Web 同时写同一会话。
- **子任务**：`delegate(user_prompt)` 创建子会话；子 Agent 使用独立配置提示词，只能通过 `submit(content)` 完成报告，不注册 delegate，可用 watch 查询或等待自身资源。未提交时最多提醒一次，仍受总轮数限制。
- **运行时输入**：用户引导与邮箱提醒共用安全交付边界及提交前屏障；完整工具组回执补齐后，同批输入只触发一次后续模型请求。用户引导仍为 user 消息；新邮件 ID 批量作为 system 运行时元数据通知，不含正文、不标记已读、不生成 UI 聊天消息。用 `read_agent_message` 读取并确认邮件；无需轮询收件。提醒不唤醒空闲主会话，已提醒 ID 持久化去重。
- **监控**：`watch(cursor, timeout)` 使用单个 Monitor 版本游标，覆盖该主会话的全部已登记资源。cursor 不是 Agent 编号；返回状态与报告路径，正文按需读取。子任务完成不会自动启动主模型。
- **审批**：审计模式下，本地写文件、编辑文件、全部 Bash 和已注册 MCP 工具均需批准本次或拒绝本次；主子会话共用规则与模式。等待审批可停止；完全访问跳过审批，仍受工具及系统权限约束。
- **引导**：Web 运行中回车先加入前端队列，可编辑或删除，点击“引导”才发送后端；CLI 回车直接提交。完整工具组回执补齐后再交付模型，已提交消息不可修改。
- **图片**：支持 PNG/JPEG/WebP；`read_image` 供模型读图，`show_image` 发布给用户，两者独立。实际视觉能力和图片数量上限由所选模型决定。
- **历史**：会话列表只读摘要，选中后通过 SSE 回放；刷新恢复当前会话，新标签页默认空会话。删除主会话会一并删除已结束的子会话与报告，有运行任务则提示先停止。
- **MCP**：按服务发现工具，每个服务连接、初始化与发现合计超时 1 秒。失败只跳过对应服务；历史工具当前未注册时返回“当前工具不可用”，不阻塞普通对话。

CLI 常用命令：`/rename 名称`、`/access audit|full_access`、`/approvals`、`/approve ID`、`/reject ID`、`/stop`、`/image 路径`、`/images`、`/send`。

## 上下文与存储

每次业务模型请求前统一检查上下文，覆盖用户输入及完整工具组之后。示例配置的触发值为 `110592` token（108K），不设固定摘要目标或框架摘要输出上限。
整理使用当前模型与独立提示词，成功后先持久化完整 messages 再更新内存；失败不替换原上下文，不新建会话。
Web 显示整理中与完成标识，CLI 输出对应文本；原始对话仍保留，恢复时以最新整理结果及后续事件组装模型消息。
Token 计数方式取决于 provider；估算值不等于模型硬上限。

```text
storage/
├── chat_ai.sqlite3            会话、事件、图片元数据、监控快照
└── sessions/<id>/
    ├── attachments/           图片与缩略图
    └── reports/               submit 报告
```

数据库复用连接，使用 WAL；流式增量采用 NORMAL，完成、取消等关键事件采用 FULL。事件提交成功后才通知界面。
会话下行统一使用 SSE：初始化 → 历史回放 → 实时事件，以 seq 续传和去重；发送、停止与审批仍通过 HTTP 命令接口。

备份包括整个 storage 目录。最简单的方法是停服务后复制；运行中数据库备份使用 SQLite backup API，不能只复制主数据库文件而遗漏 WAL。图片与报告需配套备份。

## 开发检查与后续方向

后端在项目根目录执行；前端在 `agent/web/frontend/` 执行：

```bash
python -m unittest discover -s tests -v
# 前端目录
npm test
npm run build
```

技能渐进加载、独立检索模块及 LangGraph 接入仍为待评估方向，尚未实现。
LangGraph 优先评估模型/工具循环与状态更新的接入边界，复用现有停止、审批、引导、事件与历史恢复契约；不与外部推理服务优化混在一起。
