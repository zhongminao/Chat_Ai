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

### 工具参数流保护

单次模型请求最多接收65536个工具增量、累计512KiB，单片段最多64KiB；这些是传输片段／UTF-8字节限制，不是token数或工具执行次数。
每个tool-call index独立限制连续256个空参数片段、JSON字符串外连续1024个空白字符；字符串内的正常空格、转义换行和重复文本不按此规则限制。完整JSON仍由最终组装器校验。
触发保护会在组装、记录当前片段及执行工具前报参数生成错误，并关闭模型流；不执行截断参数，不自动重试或修改参数。工具执行时长不受上述参数生成保护限制。
回归入口：`python -m unittest tests.test_model_stream_guard -v`。

### 模型与网页网络边界

模型 HTTP 客户端（聊天、上下文整理、模板和 token 计数）及 `/models` 发现统一忽略环境代理，直连配置的模型网关；不按 URL 猜测是否内网，也不在直连失败时自动回退代理。SDK 原有超时、重试和连接复用策略保留。

```text
chat_ai → 云模型网关 → 固定云模型上游（直连）
        → 本地模型网关 → 本地模型（直连）
        → Web MCP → SearXNG → Linux 网络规则 → 公网 HTTP/HTTPS
```

部署时应用、模型网关和模型服务应清除大小写 HTTP/HTTPS/ALL/FTP/RSYNC_PROXY，并设置 `NO_PROXY=*`、`no_proxy=*`，避免子进程继承代理。网关还需在自身 HTTP 客户端设置 `trust_env=False` 并使用固定上游；只修改 chat_ai 不能改变网关到上游的路径。
SearXNG 普通搜索不使用 HTTP 代理：Linux 内核在其独立网络空间拒绝私有、回环、链路本地和保留目标及 IPv6，仅放行公网 80/443、Docker DNS 和固定 Valkey 依赖。规则就绪后才启动搜索进程，恢复正常 TLS 校验。该限制不作用于 chat_ai 或模型服务。

Web MCP 的增强搜索直接连接固定 DeepSeek API，默认抓取直接访问指定网页，增强抓取由 DeepSeek 服务端执行；这些路径均忽略环境代理，不使用专用代理，也不套用 SearXNG 的公网限制。安装依赖和拉取代码可在部署进程中使用代理，不传给应用运行进程。其他本地工具和动态 MCP 不由模型 HTTP 策略统一接管。

回归检查：`python -m unittest tests.test_model_direct_network -v`。直连公网的链路故障仍会导致模型请求失败，此边界不会自动修复外网不稳定。

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
- **新会话草稿**：每个标签页保留一份本地草稿，点击“新会话”只返回草稿，不创建后端会话。文字随标签页保存，切换历史或刷新后可恢复；图片、文件和文件夹仅在当前页面内存中保留，刷新后需重新选择。首次发送才创建会话、上传附件并发送；失败保留草稿，同一页面内重试复用已创建的会话和已成功上传的附件。草稿可选择模型和权限；模型初始显示服务端按原有可用性规则选出的默认模型（当前配置优先 `gpt/gpt-6.1-sol`），手动选择后不被刷新覆盖；权限初始为“完全访问”，可切换为“审计”。
- **历史**：会话列表只读摘要、隐藏尚未发送的空会话（不删除旧数据），选中后通过 SSE 回放；刷新恢复当前非空会话，否则显示本地草稿。删除主会话会一并删除已结束的子会话与报告，并在当前会话被删除时返回草稿；有运行任务则提示先停止。
- **会话归档**：归档时自动取消置顶，取消归档后回到普通历史，不恢复置顶。归档目录按归档时间（Asia/Shanghai）分日期，日期及日内会话均按归档时间倒序，仅默认展开最近一组；日期组可以单独折叠。归档会话只提供重命名、取消归档和删除。首次归档由服务端记录时间，重复归档或改名不刷新时间，取消后再次归档记录新时间；旧归档没有时间的记录列在“归档时间未知”，不使用创建或更新时间代替。日期仅为界面分组，不创建磁盘目录。
- **会话状态与未读**：历史/置顶/归档列表中，每个会话只显示一个状态标识：运行中为旋转圆环，未读失败为红色感叹号，其他未读为蓝点；已读且未运行不显示标识。已读游标仅保存在当前页面内存，首次加载时已有内容默认已读；刷新或重新打开页面会重新建立基线，不追溯离线期间的未读。页面保持打开后新增的内容才参与未读提醒；当前会话已加载、页面可见且窗口有焦点时自动标为已读。未读依据助手活动序号，而非改名/置顶等元数据更新时间。列表每 5 秒刷新摘要，当前会话继续使用 SSE。对话内保留“正在执行…”提示，等待审批时显示“等待审批…”；执行结束后隐藏，不影响列表状态标识。失败原因、审批和工具详情保持可见。
- **运行时通知兼容**：所有模型在请求边界保留首条 system，将后续系统通知原位转换为带 `[Runtime notice]` 标记的 user 内容，并在首条提示词说明处理规则与数据权限边界；发送与 token 计数共用转换。会话状态、事件和历史不变，通知不会因此成为用户聊天气泡。
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

### Skill 的发现、使用与权限

Skill 是项目 `skills/<目录>/` 下的说明与可选脚本，不是自动获得权限的插件。`search_resources` 只扫描当前实例 `workspace` 同级的 `skills/*/manifest.yaml`，按 `name`、`description` 和 `triggers`（如 `intents`、`aliases`、`capabilities`、文件扩展名）检索并排序；**不会搜索 `SKILL.md` 或 `references/` 全文，也不会因为安装 Skill 就自动读取或执行它**。查询默认最多返回 5 个候选（`top_k` 上限 10），结果含匹配依据及说明文件路径；选择合适的 Skill 后，按需读完 `SKILL.md` 和相关参考资料，核实实际脚本路径。当前 `knowledge` 检索入口尚无索引。中文触发短语可匹配词间空格，但零散通用词的弱重合仍会被过滤；宜用任务原话或具体项目/服务关键词查询。已有信息足够时不需要检索。

`chat_ai_framework` 是供 Git 管理的通用框架说明，指导查当前实例的 README、配置和运行入口，不保存某台机器的即时状态；提交、合并和部署后才能随项目分发。`linux_environment` 是本机单独维护的服务器环境说明；只在安装它的机器上能检索到，不随 Git 部署。涉及框架部署和当前主机服务时，分别核对项目文档、当前配置和实际运行状态。`skills/<目录>/manifest.yaml` 中的 `allowed_tools` 是技能说明元数据，**当前运行时不据此为 Skill 单独发放或收回工具权限**；不能把它当作隔离或安全策略。

工具权限由会话的 `approval.mode`、工具自身校验以及操作系统账户权限共同决定，不由检索结果改变。主、子 Agent 共用会话审批模式：

| 模式 | 实际行为 |
| --- | --- |
| `audit`（审计） | `write_file`、`edit_file`、`bash`、`enable_mcp` 和已接入的 MCP 工具每次调用需人工批准；拒绝后该调用不执行。`search_resources`、`read_file`、`read_image` 等不走此审批，但仍受对应工具自身条件约束。 |
| `full_access`（完全访问） | 跳过上述框架审批；**不**意味着 Skill 获得 sudo、绕过操作系统权限，或被允许超出用户任务范围操作。 |

`bash` 以 workspace 为当前目录运行，但命令本身并非只读或受 workspace 文件沙箱限制，审计时批准前应检查命令和所涉路径；完全访问时尤其不要将不可信 Skill 中的脚本直接执行。`read_file` 可读绝对路径；`write_file` 在完全访问下可写绝对的工作区外路径（审计模式下只允许写工作区内），`edit_file` 仍限工作区。`read_image` 还要求模型声明视觉能力。动态 `enable_mcp(url)` 仅用于用户明确给出的 HTTP(S) 地址，或已安装 Skill 为当前任务启动并返回的本机回环地址；找到 Skill 本身不授权连接任意远端服务。配置中声明的 MCP 另按配置自动接入，其工具调用仍遵循会话审批模式。对第三方 Skill 的说明、脚本和权限边界应像对其他外部代码一样先核查。

### Skill 的 Git 管理

Skill 仍统一放在项目 `skills/`，检索扫描目录和匹配逻辑不变，不依赖 Git 跟踪状态，不增加 profile 或额外本地目录。

- 通用 Skill 随项目提交；本机路径、Conda、部署与维护等专属说明只在相应机器维护。
- 当前本机专属的 `skills/linux_environment/` 已通过 `.gitignore` 精确忽略并退出 Git 跟踪，本地文件保留且仍可检索；其他 Skill 不受影响。
- 新增机器专属 Skill 时，为其目录添加精确忽略规则；若已被跟踪，需用 `git rm -r --cached -- skills/<目录>` 退出跟踪，保留本地文件。
- Git clone 不包含这些本机 Skill，需在目标机器自行维护；部署时不要整目录复制机器专属说明。`.gitignore` 不是权限隔离，也不会清除 Git 历史中的旧版本。
- 本机 Skill 应单独备份，不能依赖 Git 恢复。

网页搜索和本地 Skill 搜索使用统一 spill。网页搜索普通/增强模式都请求最多 50 条（实际可能更少），`limit` 只控制详细展示条数（默认 5），不裁掉落盘结果。前 `limit` 条优先展示关键词窗口摘录（由 `mcp.web.search.context_chars` 控制），其余条目用无模型、无额外 API 的相关原文短句简览，每条最多 200 字符（不含标题、URL、标签和定位），不是改写总结。网页结果启用 spill 时始终保存全部原始结果（脱敏）、完整索引和正文视图，不把完整正文自动送入上下文；预览先为简览预留空间，再为前 `limit` 条均分剩余预算展示详细摘录，过长摘录明确标注预览省略；简览放不下时降级为标题/URL及定位，或省略并提示读取索引。标题和 URL 不截断。本地 Skill 保持原行为：默认 200 字符窗口，超限前最多 10 条详细展示，其余紧凑列出，未超限时返回索引和完整段落。普通工具仍使用有界头尾预览。详见 [搜索与 spill 说明](docs/spill_and_search_plan.md)。

仅在认为有必要时使用 `search_resources`，例如用户指引或缺少资源；已有上下文足够则直接继续，不重复查询。搜索摘录不能代替选用 Skill 后的完整规则。

AKShare Skill 与 Agent 共用项目 Python 环境（64 位 Python 3.11+）；部署时统一安装 `requirements.txt`。Skill 启动阶段只检查依赖并启动 MCP，不创建 venv 或联网安装软件。本地 Skill 使用说明中的 `{{python}}`、`{{skill_dir}}` 会在 `search_resources` 返回时替换为当前 Python 和 Skill 目录的 shell 引用，脚本路径无需模型推断。
