# chat_ai

一个同时提供 CLI 与 Web 的 Agent 框架，支持模型与工具循环、主子 Agent、工具审批、运行中引导、图像输入和自动上下文整理。
CLI 与 Web 共用运行时、状态更新和事件协议；模型推理、MCP 服务及网络代理独立部署。

## 项目结构

```text
agent/core/       Agent 装配、会话运行时、模型与工具循环、子任务监控
agent/model/      模型目录、provider、HTTP 客户端与请求消息组装
agent/agentsessionstate/   状态类型与更新、历史恢复、上下文整理、配置
agent/tools/      本地工具、统一路由、审批、输出落盘与 MCP 客户端
agent/storage/    SQLite 会话摘要与图片元数据、JSONL 事件、附件与报告
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

本开发副本 `chat_ai_test` 当前将**新会话默认模型**配置为 `gpt/gpt-6.1-sol`，**默认权限**配置为 `full_access`（完全访问，跳过工具审批，仍受工具和系统权限约束）。已有会话保留自身保存的模型和权限；显式配置、环境变量及会话选择仍遵循原有优先级。模型未被 API 发现为可用时仍使用下述原有回退策略，不保证强制使用离线模型。

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
| `spill` | 长工具输出的行数/行长和总字符预算、目录；`max_inline_chars` 默认 20000，`max_preview_chars` 默认 24000；目录必须位于工作区内 |
| `mcp` | MCP 服务别名到配置的映射，每项包含 `url`；`web.search.context_chars` 控制网页搜索每个命中前后摘录的字符数，默认 200，不传给远端服务 |

提示词里的 `{workspace}` 替换为实际工作区路径。配置或提示词变更后重启 Web/CLI。

```yaml
mcp:
  remote_windows:
    url: http://127.0.0.1:8767/mcp
  web:
    url: http://127.0.0.1:8766/mcp
    search:
      context_chars: 200
```

MCP 配置统一使用上述结构，不再接受直接写 URL 字符串的旧格式；移除 `web` 后不会加载其工具，网页摘录设置也不参与本地资源搜索。
模型连接与人工策略统一写在 `providers_file` 指向的 YAML 中，不再放在项目配置里：

- 顶层 `default_provider` 选择默认供应商；`providers.<名称>` 保留 `display_name`、`base_url`、`default_model`、`token_counter` 等连接与部署配置。`base_url_env` 可覆盖部署地址，`api_key_env` 可指定密钥环境变量。
- `providers.<名称>.defaults` 保存该供应商模型共用的 `thinking`、`vision`、`reasoning_efforts`、`default_reasoning_effort` 等人工策略。
- `providers.<名称>.models` 是 **模型 ID → 人工覆盖映射**，仅列需要覆盖默认策略的模型，不是模型清单。未列出的模型继承 `defaults`；动态发现得到的全量列表与元数据只保留在运行时，不写回 YAML。

例如，GPT 默认使用 `medium`，仅两个模型例外使用 `high`：

```yaml
providers:
  gpt:
    base_url: http://127.0.0.1:18100/gpt/v1
    api_key_default: gateway
    default_model: gpt-6.1-sol
    defaults:
      thinking: disabled
      default_reasoning_effort: medium
    models:
      gpt-6.1-sol:
        default_reasoning_effort: high
      gpt-6-sol:
        default_reasoning_effort: high
```

DeepSeek 在 `defaults` 中统一设置 `reasoning_efforts: [low, high, max]` 和 `default_reasoning_effort: high`；单模型视觉覆盖也写在对应的 `models.<模型 ID>.vision` 下。GPT 的 reasoning 配置是人工策略，不代表网关 `/models` 已返回或确认相关能力。
参数优先级为：单模型 `models.<ID>` 覆盖 > provider 的 `defaults` > API 返回值；未指定时使用程序默认值。

| 事件 | 重新读取 providers YAML | 查询模型 API `/models` | 写回 YAML |
|---|---|---|---|
| Web/CLI 启动 | 是 | 是 | 否 |
| 刷新网页或点击模型列表旁的刷新按钮 | 是 | 是 | 否 |
| 发送聊天消息 | 否 | 否 | 否 |

刷新期间保留已有模型列表，完成后替换；初次加载显示等待提示。仅无可用模型时显示模型列表刷新按钮，空列表显示“无可用模型”。接口离线或返回空列表时隐藏对应空分组，人工配置保持不变；不做后台轮询，也不发推理请求探测。`providers.yaml` 的修改可通过刷新生效，其他应用配置仍需重启。

`CHAT_AI_DEFAULT_PROVIDER` 优先于 YAML 的 `default_provider`。新会话按最近一次 `/models` 发现结果选模：默认模型可用时使用默认模型；否则优先从可用本地模型（provider 名称以 `local-` 开头）中选择，没有本地模型则随机选择一个可用云模型。选择结果保存到新会话，不修改默认配置；已有会话及子任务继承模型不变。所有模型都不可用时 UI 显示“无可用模型”，保留刷新入口。Web 启动会等待首次模型发现完成后再接受会话创建；创建会话和发送消息不额外查询模型接口，也不进行推理探活。

### 工作区文件链接

Web 提供只读文件路由：配置 `workspace` 的真实绝对路径就是 URL 前缀。例如工作区为 `/home/user/chat_ai/workspace` 时：

```markdown
[查看交接文档](/home/user/chat_ai/workspace/handoff.md)
```

点击后在新标签页访问当前服务，不必写死 `127.0.0.1`、端口或域名；路径中的空格、`#`、`?` 等字符需进行 URL 编码。这里只提供文件路由，不将消息中的裸路径自动转换为链接。

- `.md` / `.markdown` 以 UTF-8 纯文本显示（原文件应为 UTF-8），不渲染成 Markdown 阅读页。
- 图片、PDF 和普通文本可由浏览器直接查看，HTML、SVG 及其他类型作为附件下载，不执行工作区页面脚本。
- 只支持 GET/HEAD，不列目录；不存在的文件、工作区外路径以及指向工作区外的符号链接返回 404。
- 不开放整个 session 存储目录；其图片继续使用原有专用路由。
- 无签名或账号校验。任何能访问服务的人都能读取工作区内的文件，包括通过修改 URL 访问其他文件；不要将密钥等不宜公开的数据放入开放的工作区。
- 路径以当前服务的配置为准。测试副本与正式副本工作区不同，不能用另一个副本的绝对路径访问。

## 主要使用规则

- **会话与停止**：每个 session 独立持有状态，同一会话串行执行，不同会话可并发。停止会取消当前执行并关闭本地请求；停止主会话不会自动停止子任务。不要用 CLI 与 Web 同时写同一会话。
- **子任务**：`delegate(user_prompt)` 创建子会话；子 Agent 使用独立配置提示词，只能通过 `submit(content)` 完成报告，不注册 delegate，可用 watch 查询或等待自身资源。未提交时最多提醒一次，仍受总轮数限制。
- **运行时输入**：用户引导与邮箱提醒共用安全交付边界及提交前屏障；完整工具组回执补齐后，同批输入只触发一次后续模型请求。用户引导仍为 user 消息；新邮件 ID 批量作为 system 运行时元数据通知，不含正文、不标记已读、不生成 UI 聊天消息。用 `read_agent_message` 读取并确认邮件；无需轮询收件。提醒不唤醒空闲主会话，已提醒 ID 持久化去重。
- **监控**：`watch(cursor, timeout)` 使用单个 Monitor 版本游标，覆盖该主会话的全部已登记资源。cursor 不是 Agent 编号；返回状态与报告路径，正文按需读取。子任务完成不会自动启动主模型。
- **审批**：审计模式下，本地写文件、编辑文件、全部 Bash 和已注册 MCP 工具均需批准本次或拒绝本次；主子会话共用规则与模式。等待审批可停止；完全访问跳过审批，仍受工具及系统权限约束。
- **引导**：Web 运行中回车先加入前端队列，可编辑或删除，点击“引导”才发送后端；运行结束后输入框直接发送普通消息，包括撤回编辑的内容，不受已有队列影响。队列中其他内容保留，不自动发送。CLI 回车直接提交。完整工具组回执补齐后再交付模型，已提交消息不可修改。
- **图片**：支持 PNG/JPEG/WebP；`read_image` 供模型读图并返回会话附件路径与 Markdown 引用；要展示给用户时，将返回的 Markdown 原样放入回复或报告，仅检查不自动展示。实际视觉能力和图片数量上限由所选模型决定。
- **历史**：会话列表只读摘要，选中后通过 SSE 回放；刷新恢复当前会话，新标签页默认空会话。删除主会话会一并删除已结束的子会话与报告，有运行任务则提示先停止。
- **会话状态与未读**：历史/置顶/归档列表中，每个会话只显示一个状态标识：运行中为旋转圆环，未读失败为红色感叹号，其他未读为蓝点；已读且未运行不显示标识。已读游标仅保存在当前页面内存，首次加载时已有内容默认已读；刷新或重新打开页面会重新建立基线，不追溯离线期间的未读。页面保持打开后新增的内容才参与未读提醒；当前会话已加载、页面可见且窗口有焦点时自动标为已读。未读依据助手活动序号，而非改名/置顶等元数据更新时间。列表每 5 秒刷新摘要，当前会话继续使用 SSE。对话内保留“正在执行…”提示，等待审批时显示“等待审批…”；执行结束后隐藏，不影响列表状态标识。失败原因、审批和工具详情保持可见。
- **时间**：每个新 turn 开始时按 Asia/Shanghai 读取一次系统时间，以隐式 system 消息提供给模型；同一 turn 的模型/工具循环及用户引导不重复注入。时间快照随 turn.started 内部事件保存，恢复时保留原值；Web/CLI 不将它渲染为聊天消息。
- **MCP**：创建 Agent 时按配置发现工具，每个服务连接、初始化与发现合计超时 1 秒。失败只跳过对应服务；用户明确提供新的 HTTP(S) MCP 地址，或本地已安装 Skill 为当前任务启动服务并返回本机回环地址时，可用 `enable_mcp(url)` 主动接入（审计模式下仍需审批）；不要求将地址写入配置。AKShare Skill 随项目携带，共用 Agent 的项目 Python 环境，在本机按需启动原版 AKTools，保留完整接口，使用启动结果返回的实际地址，不依赖固定 Conda 名称、常驻服务或宿主机转发。连接成功后仅在整批工具调用结束后注册，供当前用户请求的下一次模型调用使用；成功接入的地址会随会话恢复，重复启用不会再次发现；历史工具当前未注册时返回“当前工具不可用”，不阻塞普通对话。

CLI 常用命令：`/rename 名称`、`/access audit|full_access`、`/approvals`、`/approve ID`、`/reject ID`、`/stop`、`/image 路径`、`/images`、`/send`。

## 上下文与存储

每次业务模型请求前统一检查上下文，覆盖用户输入及完整工具组之后。示例配置的触发值为 `110592` token（108K），不设固定摘要目标或框架摘要输出上限。
整理使用当前模型与独立提示词，成功后先持久化完整 messages 再更新内存；失败不替换原上下文，不新建会话。
Web 显示整理中与完成标识，CLI 输出对应文本；原始对话仍保留，恢复时以最新整理结果及后续事件组装模型消息。
Token 计数方式取决于 provider；估算值不等于模型硬上限。

```text
storage/
├── chat_ai.sqlite3            会话摘要、图片元数据、邮箱与监控快照
└── sessions/<id>/
    ├── events.jsonl           完整事件日志，历史恢复的权威数据
    ├── attachments/           图片与缩略图
    └── reports/               submit 报告
```

数据库复用连接，使用 WAL。事件写入 JSONL，关键边界执行 fsync 后更新 SQLite 摘要，再通知界面；流式增量不逐条更新摘要。摘要可从日志恢复，日志缺失时需从备份恢复。旧 SQLite 事件迁移工具已移除。
日志使用内存稀疏偏移索引，重复读取可跳过已校验的前缀；外部写入或文件变化会触发重新校验，索引不产生额外持久化文件。
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

本开发副本默认修改 `chat_ai_test`；不自动发布至其他副本。

### Skill 的 Git 管理

Skill 仍统一放在项目 `skills/`，检索扫描目录和匹配逻辑不变，不依赖 Git 跟踪状态，不增加 profile 或额外本地目录。

- 通用 Skill 随项目提交；本机路径、Conda、部署与维护等专属说明只在相应机器维护。
- 当前本机专属的 `skills/linux_environment/` 已通过 `.gitignore` 精确忽略并退出 Git 跟踪，本地文件保留且仍可检索；其他 Skill 不受影响。
- 新增机器专属 Skill 时，为其目录添加精确忽略规则；若已被跟踪，需用 `git rm -r --cached -- skills/<目录>` 退出跟踪，保留本地文件。
- Git clone 不包含这些本机 Skill，需在目标机器自行维护；部署时不要整目录复制机器专属说明。`.gitignore` 不是权限隔离，也不会清除 Git 历史中的旧版本。
- 本机 Skill 应单独备份，不能依赖 Git 恢复。

网页搜索和本地 Skill 搜索使用统一 spill：搜索模块提供匹配词附近的原文摘录（本地 Skill 固定默认 200 字符，网页由 `mcp.web.search.context_chars` 控制），超限预览前最多 10 条详细展示、其余紧凑列出，标题和 URL 不截断，放不下的条目留在完整索引。超限时由 spill 保存原始结果、完整索引和按行读取的正文视图；未超限时摘要在前、完整段落在后。普通工具继续使用有界头尾预览，见 [搜索与 spill 说明](docs/spill_and_search_plan.md)。

仅在认为有必要时使用 `search_resources`，例如用户指引或缺少资源；已有上下文足够则直接继续，不重复查询。搜索摘录不能代替选用 Skill 后的完整规则。

更进一步的技能渐进加载、独立知识检索模块及 LangGraph 接入仍为待评估方向，尚未实现。
LangGraph 优先评估模型/工具循环与状态更新的接入边界，复用现有停止、审批、引导、事件与历史恢复契约；不与外部推理服务优化混在一起。

AKShare Skill 与 Agent 共用项目 Python 环境（64 位 Python 3.11+）；部署时统一安装 `requirements.txt`。Skill 启动阶段只检查依赖并启动 MCP，不创建 venv 或联网安装软件。本地 Skill 使用说明中的 `{{python}}`、`{{skill_dir}}` 会在 `search_resources` 返回时替换为当前 Python 和 Skill 目录的 shell 引用，脚本路径无需模型推断。
