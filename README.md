# chat_ai

## 开发约定

生产代码尽量保持简洁，模块职责清晰，功能通过小模块组合。提高可维护性所需的适当代码增量是合理的，不以减少行数作为唯一目标，也不为拆分而增加无必要的封装。测试代码的行数增量不作为生产代码设计的限制，测试关注有效覆盖和实际行为。

简单的状态操作集中在同一个模块，较大的状态变更逻辑单独成文件。CLI、Web 和核心运行时共用事件流；界面逻辑不进入核心。文档只记录真实行为和必要入口。

## 当前结构

```text
agent/core/       Agent 装配、SessionRuntime、AgentRuntime、会话调度与运行资源
agent/model/      模型协议、provider、模型目录与客户端复用、图文消息组装
agent/tools/      本地工具、schema、router、spill
agent/tools/mcp/  MCP 客户端与结果转换
agent/mcp_servers/ 独立 MCP 服务端
agent/storage/    session、events.jsonl、图片与缩略图
agent/workflow/   state 类型、状态节点、流程路由、历史恢复、配置与输入命令
agent/cli/        CLI
agent/web/        FastAPI、SSE、页面
config.yaml       项目配置
prompts/          框架实际加载的模型提示词
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

上述手动启动示例访问 `http://127.0.0.1:8764`；FastAPI 提供 `dist/index.html`、`/assets` 和原有 `/api`。
服务器当前生产服务为用户级 `chat_ai.service`，监听 `8200`；模型仍由 provider 配置选择。

```bash
systemctl --user status chat_ai
systemctl --user restart chat_ai
journalctl --user -u chat_ai -f
```

前端开发时保持上述 FastAPI 服务运行，在另一个终端执行：

```bash
cd /home/zhong/mydisk/tools/chat_ai/agent/web/frontend
npm run dev
```

访问 `http://127.0.0.1:5173`，Vite 默认将 `/api` 代理到手动启动示例的 `127.0.0.1:8764`。
若使用现有生产服务作为开发后端，需要将 `vite.config.ts` 中的代理目标调整为 `127.0.0.1:8200`。
前端检查：`npm test`；`npm run build` 包含 TypeScript 检查。
后端检查（项目根目录、py313 环境）：`python -m unittest discover -s tests -v`。
取消回归使用本地模拟 HTTP 端点覆盖等待响应、等待流数据、部分输出后停止及会话后续执行，不需要真实模型请求。

修改 Python 后端或 provider 适配代码后，需要重启 uvicorn；修改前端后需要重新构建并刷新页面。
当前生产网页服务端口为 8200，手动开发示例为 8764；8002 是本地千问的模型服务端口，两者独立启动。

## 前端模块

```text
agent/web/frontend/src/
├── app/                         应用布局与模块接入
├── api/                         HTTP、SSE 与类型定义
├── state/                       历史回放与实时事件 reducer
├── features/
│   ├── sessions/                会话列表与选择
│   ├── models/                  模型选择器
│   ├── images/                  上传草稿、图片卡片与名称编辑
│   ├── watch/                   后台任务状态展示与订阅
│   └── conversation/            消息列表、输入框与对话状态
│       └── content/             Markdown、代码、公式与流式显示
└── ui/                          通用界面组件
```

前端按职责组织：`features/` 包含会话、对话、图片和模型选择，`api/` 封装原有 HTTP/SSE，
`state/` 统一处理历史事件回放与实时事件，`styles.css` 管理样式。
用户消息保留纯文本；助手回复通过 `features/conversation/content/MarkdownContent.tsx` 展示 Markdown。
内容扩展入口是 `MessageContent.tsx`，正文、表格和代码样式位于 `content/content.css`。
`CodeBlock.tsx` 提供语言标签、复制与代码框；`codeHighlight.ts` 按需加载并复用 Shiki 高亮器。
支持 Python、Bash、JavaScript、TypeScript、JSX、TSX、JSON、YAML、HTML、CSS、SQL 和 Diff；
未知语言按原文展示。扩展代码语言时在 `codeHighlight.ts` 添加加载器与标签即可。
公式支持独立行的双美元符号块和显式 math 围栏，由 `content/MathBlock.tsx` 使用 KaTeX 排版。
`content/mathBlocks.ts` 只注册块级数学语法，正文中的单美元符号和行内双美元符号保持文本。
公式分隔符未闭合时展示源码，闭合后渲染；解析失败保留源码，成功时可展开和复制 LaTeX。
数学 CSS 和字体随前端构建发布，不依赖 CDN。
正在生成的助手回复通过 `content/useStreamingText.ts` 按文本到达速率柔和显现，
原始消息状态保持完整，历史消息立即展示；代码和表格在自身区域横向滚动。
事件订阅使用现有 `after`/`Last-Event-ID` 协议，切换会话会关闭旧连接；首屏从现有事件流回放历史。
首次打开或刷新网页默认进入空会话，不再自动恢复上次选中的历史；历史会话由用户从侧栏点击打开。
初次加载和新建按钮共用空会话选择逻辑，优先复用没有消息且未运行的主会话，找不到才创建；
根据已加载的摘要筛选候选，再通过 conversation 接口确认是否仍为空，连续点击不会反复创建空记录。
新建不再先查询一次完整列表，选中空会话后在后台刷新列表，不阻塞输入框加载。

会话列表由 SessionStore.read_list_summary() 提供标题、状态、是否为空和更新时间等摘要，不重建消息历史。
每个会话的 summary.json 是可重建的列表缓存，包含事件文件标识、大小、修改时间和完整行读取位置；
未变化时直接复用，日志追加时仅解析新增完整事件。旧历史首次生成一次摘要，服务重启后仍可复用；
缓存损坏、日志截断或替换时重建，自定义标题仍读取 session.json。摘要不是 AgentState checkpoint。
仅点击具体会话时通过现有 conversation/events 接口读取和恢复完整历史；会话删除会一并删除摘要。
纯文本调用与旧事件兼容，图片引用通过同一消息和事件流程处理。

## 会话名称

Web 会话列表中的铅笔按钮可修改名称；按 Enter 或点击勾号保存，Esc 或取消按钮放弃修改。
保存后列表和顶部主／子 agent 导航的悬停说明一起更新。名称需要 1–80 个字符，前后空白会被移除，不能包含换行或控制字符。
CLI 在当前会话中输入 `/rename 图片识别实验`，也可以修改同一个名称。

Web 的 `PATCH /api/sessions/{id}` 接收 `{"title":"新名称"}`，与 CLI 共用
`agent/storage/session.py` 的 `SessionStore.rename(session_id, title)`，统一校验并原子写入 `session.json`。
自定义标题保存在会话元数据中；没有自定义标题的会话根据首条用户消息生成名称。收到 turn.started 后立即刷新列表，命名不等待模型回复结束；空会话显示“新会话”，自定义标题优先。
改名不会修改会话 ID、历史消息或模型上下文；名称可重复，运行中也可修改。
CLI 修改名称后，Web 刷新页面或重新加载会话列表即可看到。空会话的复用依据实际消息判断。
前端的单行展示和编辑位于 `features/sessions/SessionRow.tsx`，保存状态由 `useSessions.ts` 管理。

前端内容渲染所用的开源项目及官方地址：

| 项目 | 用途 | 项目地址 |
| --- | --- | --- |
| react-markdown | 将 Markdown 渲染为 React 组件 | [remarkjs/react-markdown](https://github.com/remarkjs/react-markdown) |
| remark-gfm | 表格、任务列表、删除线等 GFM 语法 | [remarkjs/remark-gfm](https://github.com/remarkjs/remark-gfm) |
| Shiki | 代码语法高亮、语言与主题加载 | [shiki.style](https://shiki.style/) |
| KaTeX | LaTeX 数学公式排版 | [katex.org](https://katex.org/) |
| micromark-extension-math | Markdown 数学语法解析，本项目限制为块级公式 | [micromark/micromark-extension-math](https://github.com/micromark/micromark-extension-math) |
| mdast-util-math | 数学语法与 Markdown 语法树之间的转换 | [syntax-tree/mdast-util-math](https://github.com/syntax-tree/mdast-util-math) |

## Agent 轮数与系统提示词

CLI 和 Web 共用根目录 `config.yaml` 的运行配置。`storage_dir: ./storage` 指定存储根目录，实际日志位于 `storage/sessions/<id>/events.jsonl`；旧的 `event_log` 配置键已改为 `storage_dir`，使用自定义配置时也需更新，不移动已有数据。

运行轮数和提示词配置：

```yaml
max_rounds: 200
system_prompt_file: ./prompts/main_agent.md
child_system_prompt_file: ./prompts/child_agent.md
```

主 Agent 每次用户请求、子 Agent 每次委派任务各自最多执行 `max_rounds` 轮模型调用，默认均为 200；一轮可包含多个工具调用。
delegate 只接受 user_prompt，包含完整任务、角色要求、上下文和路径；子 Agent 使用配置指定的 child_agent.md，继承模型与轮数上限。达到上限会结束该任务并更新 watch 状态。
`max_rounds` 必须为正整数；`system_prompt_file`、`child_system_prompt_file` 指向主、子 Agent 完整提示词文件。
路径以 config.yaml 所在目录为基准，也支持绝对路径；文件必须是非空 UTF-8 文本。直接编辑 prompts/main_agent.md、prompts/child_agent.md，框架不再额外拼接系统提示词。
提示词中的 `{workspace}` 替换为实际工作区绝对路径，其他花括号原样保留，支持直接写入 JSON 示例。
配置在创建运行资源时加载；修改后重启 Web 和 CLI，即可让新旧会话按主、子角色使用最新配置，不改写历史日志。旧子会话元数据中的 system_prompt 保留，但不再覆盖配置。

## 图片输入与名称

Web 支持选图、粘贴和拖入静态 PNG/JPEG/WebP；每张最多 10 MB、2000 万像素，每条消息最多 8 张。
图片按会话分配固定编号 01、02、03 等；名称默认使用原文件名，允许重名。
附件与工具输出标签显示为 `01 / 曲线图.png`。在附件卡片中编辑名称，按 Enter 或移开焦点保存；改名不改变编号、资源 ID 或保存路径。
模型收到每张输入图片的编号、当前名称和完整会话文件路径；编号与名称用于描述，工具调用只使用路径。
旧会话中与 first/second 等旧自动名称相同的名称兼容显示为原文件名；其他自定义名称、已有编号和路径保留，历史日志不改写。
待发送与历史图片使用相同名称；运行中暂不能改名。消息可以只包含图片。
移除草稿附件只取消本次发送，文件保留在会话中；删除整个会话会一起删除附件。

公共模块：

```text
agent/storage/images.py     图片文件、缩略图、默认名称与重命名
agent/workflow/input.py     CLI/Web 共用的 UserInput
agent/model/request_messages.py     图片说明与模型消息组装
```

原文件及名称保存在 session 的 attachments/ 中；events.jsonl 和 state 只保存引用及元数据，
模型请求时读取原文件并编码为 Base64。每张图片前有独立说明，包含原编号和当前名称。
历史恢复使用相同资源 ID，后续请求会读取最新名称。模型及转发服务需要支持视觉输入。

CLI 一次输入两张图：

```bash
python -m agent.cli.main "比较 01 和 02" --image /path/a.png --image /path/b.jpg
```

自定义名称用重复的 --image-name 与 --image 一一对应。交互命令：

```text
/image /path/a.png                 添加图片到下一条消息
/image /完整会话路径/attachments/<image_id>.png  引用已有会话图片
/image-name /完整会话路径/attachments/<image_id>.png "设备整体"  修改显示名称
/images                            列出编号、名称和完整会话路径
/send                              只发送待发送图片
/clear-images                      取消本次待发送图片
```

Web 的图片接口是公共能力的薄适配：GET/POST /api/sessions/{id}/images、
PATCH /api/sessions/{id}/images/{image_id}、GET /api/sessions/{id}/images/{image_id}/content。
前端图片模块位于 features/images/，Composer 和 MessageList 负责接入。

## 工具图片输出

Python 绘图、截图等工具先生成图片文件，再调用共用工具 `show_image`：

```json
{"path":"plots/result.png","name":"实验结果"}
```

`path` 可以是工作区相对路径或绝对路径；已有图片优先使用返回的完整会话保存路径，不能用编号、名称或 ID 代替路径。
`name` 可省略，新图片默认使用原文件名，已有图片沿用当前名称；显式提供 `name` 会更新显示名称，允许重名。
该工具只发布已有静态 PNG/JPEG/WebP 文件，大小限制与上传图片一致，不调用生图 API。
模型使用 Python 时应将图保存为文件，例如 `plt.savefig("plots/result.png")`，然后调用 `show_image`。

Web 与 CLI 使用同一份 schema 和工具执行逻辑：Web 在工具详情之外直接显示图片，支持查看原图和下载；
CLI 只打印图片名称、原文件路径和保存路径，不依赖图形界面或终端图片协议。
通过 SSH 使用 CLI 时，路径对应服务器文件，可自行下载。

图片复制到当前 session 的 attachments/；覆盖或移除原绘图文件不影响已发布图片。
`tool.completed` 的 `result` 保持文本，新增可选的 `images` 元数据用于界面显示和历史回放。
传给模型的工具消息仍为文本；图片不会自动回传给视觉模型。旧字符串工具结果和旧事件继续兼容。
子 agent 的图片保存在独立 session。submit 将已展示图片的 Markdown 地址写入报告；主 agent 读到报告后可直接引用这些地址。

```text
agent/tools/images.py                       show_image，共用图片发布逻辑
agent/tools/result.py                       文本与图片引用的 ToolResult
agent/cli/output.py                         CLI 路径展示
agent/web/frontend/src/features/images/ImageOutput.tsx 网页图片展示
```

## 模型主动读图

共享工具 `read_image` 把图片作为视觉输入提供给当前模型：

```json
{"path":"plots/result.png"}
```

支持工作区相对路径和绝对路径，文件格式、大小与现有图片限制一致。
新文件保存为会话图片快照；再次读图或展示同一会话路径会复用资源 ID 和编号。
再次使用原文件路径时，文件字节与已有快照相同也会复用（SHA-256 比较）；覆盖后内容改变则分配新编号，旧快照保留。
旧附件没有 SHA-256 时从文件计算，无需重写历史日志。上传新附件仍分配新编号；已有附件改名不改变引用。
`read_image` 供模型检查图片，`show_image` 供用户查看图片，两者分别控制，不会自动互相调用。
例如：生成 PNG → read_image 检查 → 修改脚本 → show_image 展示最终结果。

Web 和 CLI 使用相同工具及模型请求流程，不增加手动操作入口。
工具结果的 `model_images` 保存视觉引用，与网页展示用的 `images` 分开。
事件和消息状态只保存元数据及资源 ID；历史恢复后仍可使用对应图片。
实际请求时，在全部工具回执之后附加标明工具来源的 user 图像内容，满足 Chat Completions 的消息格式。
这条附加内容仅存在于模型请求中，不新增用户消息气泡或 turn.started 事件。
同一个请求中的相同图片 ID 只编码一次，后续引用保留名称提示。

视觉能力由 `agent/model/providers/providers.yaml` 声明，模型条目优先于 provider 默认值。
当前只为已验证的本地千问 9B 设置 `vision: true`、`max_images: 8`。
其他模型确认接口支持后，可声明 `vision: true`，并按服务限制设置 `max_images`。
未声明支持视觉时，read_image 返回工具错误，不切换模型、不中断整轮对话。
切换到非视觉模型后，历史读图引用保留，请求中不附加其图像内容。
本地千问的 8 张上限计算整个模型上下文（含用户图片和此前主动读图）；达到上限后可使用新会话，代码不会自动裁剪历史。

实现入口：`agent/tools/images.py`、`agent/tools/result.py`；消息组装位于 `agent/model/request_messages.py`，
能力配置读取位于 `agent/model/catalog.py`，历史恢复位于 `agent/workflow/message_replay.py`。

## 模型配置与本地服务

模型目录位于 `agent/model/providers/providers.yaml`，Web 和 CLI 共用该配置。

| Provider | 当前用途 | 接口 |
| --- | --- | --- |
| `deepseek` | 默认模型 `deepseek-flash` | DeepSeek API |
| `gpt` | GPT 模型选择 | passion8 网关 |
| `local-qwen3p5-9b` | 本地千问 9B，图片识别 | `http://127.0.0.1:8002/v1` |

远程模型 API 密钥由 provider 配置中的 `api_key_env` 指定，例如 `DEEPSEEK_API_KEY`、`GPT_API_KEY`。
测试图片时，在模型选择器中切换到本地 `local-qwen3p5-9b`。
图文请求使用共用的 `agent/model/request_messages.py`。通用 `OpenAICompatibleAdapter` 位于 `model/openai_compatible.py`，供 GPT、Qwen 等使用；`providers/qwen.py` 的 `QwenChatTemplateAdapter` 专门配置 Qwen 模板的思考开关。
本地请求根据 provider 的 `thinking` 配置传递 `chat_template_kwargs.enable_thinking`，当前为 `disabled`。
思考过程的前端展示尚未实现。

### 本地千问 9B 默认启动配置

服务文件：`/home/zhong/.config/systemd/user/local-qwen3p5-9b.service`。
systemd 的 `ExecStart` 直接执行 `vllm serve`，当前配置如下：

| 设置 | 默认值 |
| --- | --- |
| 模型目录 | `/home/zhong/mydisk/model/Qwen-9B/Qwen_3p5_9B` |
| 服务模型名 / 端口 | `local-qwen3p5-9b` / `8002` |
| 权重量化 / KV cache | FP8 / FP8 |
| 视觉模块 | 启用 |
| 最大上下文 | 131072 token（128K，输入与输出共用） |
| 最大并发 | 1 |
| 显存预算 | `--gpu-memory-utilization 0.89` |
| 注意力后端 | `TRITON_ATTN`，适配当前 Blackwell 显卡 |
| 图片上限 | 每个完整模型请求（含历史）最多 8 张 |
| 视觉预处理 | 65536–786432 像素；上传原文件保持不变 |
| 工具调用解析 | `qwen3_xml` |
| 前缀缓存 | 启用 |

RTX 5060 Ti 16GB 上本次启动实测：模型进程约占 13.6 GiB，KV cache 约 2.54 GiB，
缓存容量约 157086 token。该数据是当前配置的启动记录，实际占用会随版本、编译缓存和请求变化。

```bash
systemctl --user start local-qwen3p5-9b
systemctl --user stop local-qwen3p5-9b
systemctl --user status local-qwen3p5-9b
journalctl --user -u local-qwen3p5-9b -f
```

修改 service 后加载配置并重启：

```bash
systemctl --user daemon-reload
systemctl --user restart local-qwen3p5-9b
```

服务已设置为用户级自启动。首次启动需要加载权重、量化和编译；`active` 不代表模型接口已经就绪，
可用以下只读接口检查：

```bash
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/v1/models
```

参考脚本 `/home/zhong/mydisk/tools/chat/start_local_qwen3p5_9b.sh` 保留原有纯文本配置，
手动执行它会使用脚本中的参数；当前视觉部署以以上 systemd 服务配置为准。

### 输出与显示排查

若回答出现语言混杂，先检查 session 的 `events.jsonl` 中对应的 `message.delta`。
若原始输出已经含有同样文字，则应从模型输出和生成参数排查。
阿拉伯语等正常 Unicode 文字可以直接展示；混用语言或语句不通顺属于输出质量问题，
需要与字符损坏、缺字和显示异常区分。

## 状态与运行时

每个 session 独立持有一份可 JSON 序列化的 `AgentState`，传给自己的 `AgentRuntime` 使用：

- `role`：`main` 或 `child`，根据会话父子关系初始化，不新增持久化身份字段。
- `model`：当前 provider、模型名称和 thinking 设置。
- `messages`：系统提示词、用户与助手消息、工具调用和结果；图片保存资源 ID 引用。
- `execution`：本轮 ID、状态、阶段、轮次、回复、submit 报告及路径、补交提醒次数 completion_reminders、错误；尚未执行时为 null。

状态节点只读取输入数据并返回 `StateUpdate`，不原地修改输入、不创建客户端、不执行工具，也不写日志或文件。
运行时应用更新、执行 I/O 并发布事件。流程路由由 `after_model`、`after_tools` 决定下一步。

| 模块 | 职责 |
| --- | --- |
| `workflow/state.py` | `AgentState`、`ExecutionState` 和 `StateUpdate` 类型 |
| `workflow/completion.py` | 根据 role 和本轮状态判断结束、一次补交提醒或失败；不执行 I/O |
| `workflow/transitions.py` | 简单操作合集：切换模型、执行生命周期、流式回复累积、submit，以及流程路由 |
| `workflow/message_updates.py` | 用户输入、模型回复、工具结果、取消时保留部分回复等消息变更 |
| `workflow/context_compaction.py` | 上下文整理条件、保留范围、摘要替换及大小校验，返回 StateUpdate |
| `workflow/message_replay.py` | `restore_display_messages` 恢复完整展示历史；`restore_model_messages` 恢复模型上下文 |
| `core/agent_factory.py` | 构建初始 state、选择主子提示词、配置工具和装配 AgentRuntime |
| `core/session_runtime.py` | 独立持有 state，管理会话队列、线程、忙闲、停止、报告保存和退出清理 |
| `core/agent_runtime.py` | 调度本轮模型与工具循环，应用节点更新并发布事件 |
| `model/catalog.py` | 模型配置校验、视觉能力，以及 `get_binding(target)` 请求资源与 provider 复用 |
| `model/http_client.py` | `ModelHttpClient` 复用模型连接，执行可取消 HTTP 请求并关闭资源；异步网络 I/O 适配同步模型流接口 |

切换模型只更新 state 并记录事件，不要求初始化 agent 执行器、MCP 或模型客户端。
实际调用模型时，`get_binding` 按目标模型按需创建资源；同一个 catalog 实例只复用当前模型的一对资源，目标改变后重新创建。
新资源创建成功后才替换并关闭旧绑定。绑定按实例隔离，不跨 session 共享。模型请求资源持有独立事件循环，由现有 session worker 驱动，不另建后台线程；worker 退出时关闭资源。
客户端、provider 实例、连接、线程、锁、队列、回调和工具路由留在运行时；工具 schema 和 MCP 配置不复制进 `AgentState`。

`agent/core/control.py` 提供运行控制状态。Web 和 CLI 共用 `ExecutionControl`，控制信号不写入 `AgentState`。
Web 通过 `POST /api/sessions/{session_id}/control/stop` 请求停止，CLI 使用 `Ctrl+C`。
模型请求在建立连接、等待响应和读取流时均接入取消；停止会取消本次网络操作、关闭对应流并等待本地清理，再发出 turn.cancelled。Web 在此之前显示“正在停止”，收到终止事件后恢复输入。
已请求停止导致的请求异常按取消处理，未请求停止的网络异常仍为失败。这里的“已停止”只表示本地本轮执行已结束；使用标准请求取消和连接关闭向请求接收端传达中断，不查询或确认模型服务端是否停止生成，也不关闭其他会话的请求。
`SessionRuntime.busy` 表示调度器是否有任务在执行，`execution.status` 描述本轮逻辑结果；二者不等同于 watch 的资源状态。

当前不保存整个 state checkpoint，也不序列化运行资源。`events.jsonl` 保持为持久化事件流；
CLI 和 Web 共用运行时，模型输入由 `restore_model_messages` 恢复，网页完整历史由 `restore_display_messages` 恢复。
工具输出过大时写入工作目录 `.spill/<session_id>/`，模型通过 `read_file` 读取。

## 自动上下文整理

CLI、Web、主子 Agent 共用每次业务模型请求前的检查入口，覆盖新用户输入、整组工具结果和补交提醒之后。
默认在 110592 token（120K 的 90%，即 108K，K=1024）时整理：

```yaml
context:
  enabled: true
  trigger_tokens: 110592
  prompt_file: ./prompts/context_compaction.md
```

`trigger_tokens` 必须是正整数，修改后重启服务。
不再设置 `target_tokens`、`summary_max_tokens`，提示词也不规定字数；模型按当前任务需要决定摘要详略。
`prompts/context_compaction.md` 是发给摘要模型的纯提示词；本节 README 是给操作者看的说明，不作为模型输入。
框架不传摘要输出 token 上限，模型服务自身的上下文窗口和输出限制仍然有效。
关闭 `enabled` 后不统计、不调用摘要模型，已保存的整理结果仍正常恢复。
统计包括系统提示词、消息和工具定义。30B provider 配置 `token_counter: llama_cpp`，通过服务端
`/apply-template` 和 `/tokenize` 实际计数；其他 provider 暂按 UTF-8 字节约三分之一及每图 4096 token 估算，
估算不是模型硬上限，视觉费用也可能不同。token_counter 是 provider 能力，触发阈值仍在 config.yaml。

`workflow/context_compaction.py` 是整理状态更新入口，不创建客户端或写文件；它保留系统提示词、最新用户原文（含图片引用）
以及最近完整的助手／工具组，其余历史交给当前模型生成摘要。长工具循环在同一用户轮次内也能整理。
`model/context_summary.py` 使用独立提示词、无工具的单次可取消请求，不递归运行 AgentRuntime，不消费业务模型轮数，
不修改 answer、report 或 submit 提醒状态，也不重新读取文件或图片。摘要保留观察结论与引用，必要时业务模型再读取。
摘要准确性取决于模型，结构与大小校验通过不表示语义无损。

Runtime 在校验成功后先写入 `context.compacted` 事件中的完整 messages，再 apply 更新，不新建会话、不改写旧事件。
`message_replay.restore_model_messages` 从最新整理结果恢复，再追加后续事件；配置未变化时与保存的上下文一致。
显式修改角色系统提示词仍会更新恢复后的首条系统消息，沿用原配置行为。
网页 conversation 接口继续使用 `restore_display_messages` 还原完整原始历史，模型摘要不冒充用户消息显示。
整理后须确实缩小且低于触发阈值，以免下一轮立即再次整理；不要求固定大小或压缩比例。
摘要失败、截断、未缩小、仍达到触发阈值或落盘前取消均不替换原上下文，不无限重试；失败结束本轮并保留错误供用户处理。
当前输入或最后工具组过大、没有可整理历史时明确报错，不静默裁剪。

共享反馈事件为 `context.compaction.started`、`context.compacted`、`context.compaction.failed`、`context.compaction.cancelled`。
Web 整理时显示“正在自动压缩上下文”，成功后留下灰色“上下文已自动压缩”标识，刷新和历史回放可恢复，
submit 折叠过程时标识仍可见；失败或取消显示对应状态，重启后的未完成整理显示中断。
CLI 消费同样事件输出文本。摘要正文不进入普通 message.delta，避免混入回复或历史气泡。
旧的跨会话交接实验代码已删除。生产整理由 agent/workflow/context_compaction.py 返回状态更新，Runtime 调用摘要、持久化并应用更新；不运行外部脚本或加载 skill。

## MCP 与网页工具

`config.yaml` 中配置 MCP URL：

```yaml
mcp:
  web: http://127.0.0.1:8766/mcp
```

MCP 工具在 Agent 创建时按服务分别发现；每个服务的连接、初始化和工具发现合计最多等待 1 秒。
连接失败或超时只记录该服务的告警并跳过其工具，继续注册其他服务，不阻止普通对话和本地工具使用。
已经注册的 MCP 工具在调用时断开，返回对应工具错误，不终止整个会话。
ToolRouter 以本轮已注册工具列表为准；模型再次调用历史中已不可用的 MCP 工具或其他未注册工具时，
返回“当前工具不可用”的工具回执，后续工具和模型循环继续，不改写历史调用记录。
当前不增加后台重试或连接管理器；服务恢复后新建会话，或重启 Web／CLI 重新打开原会话，可重新发现工具。
告警在 CLI stderr 或 Web 服务日志中查看。

搜索桥接请求本地 SearXNG 时保持直连；`fetch_url` 读取 HTTP_PROXY/HTTPS_PROXY 等环境变量访问外部网页。
使用终端代理时同时设置 `NO_PROXY` 和 `no_proxy` 为 `localhost,127.0.0.1,::1`，避免本地 MCP 和模型接口绕到代理。
当前用户服务的固定代理配置位于 `~/.config/systemd/user/chat-search-mcp.service.d/20-proxy.conf`；终端的 `proxy_on`/`proxy_off` 不会修改已运行服务的环境。修改服务配置后执行 `systemctl --user daemon-reload` 并重启 `chat-search-mcp.service`。

`agent/mcp_servers/web.py` 提供：

配置连接别名为 `web`，工具名为 `mcp_web_search` 和 `mcp_web_fetch_url`。

- `search`：调用本地 SearXNG 搜索网页
- `fetch_url`：读取公开网页的静态 HTML 文本

SearXNG 是搜索后端；`web.py` 是独立的 Web MCP 服务端。`fetch_url` 不执行 JavaScript，也不提供登录和浏览器操作。

## 下一阶段：混合检索

目标是组合关键词检索和向量检索：

```text
查询
→ 关键词召回
→ 向量召回
→ 合并、去重、排序
→ 返回统一结果
```

先保持检索模块独立，不把索引、向量库和排序逻辑放进 `AgentRuntime`。具体数据源、向量模型和存储方式在实现前单独确定。


## Watch 多 agent

- `delegate(user_prompt)`：创建独立子 session，立即返回 ID 和 watch 使用提示。子 Agent 系统提示词由 config.yaml 的 child_system_prompt_file 指定，不接受主 Agent 覆盖。
- `watch(cursor=None, timeout=0)`：无 cursor 返回资源快照；有 cursor 返回其后变化的资源；timeout>0 时等待任意变化，最多 120 秒。超时返回空 changes，游标不变。
- `submit(content)`：保存本轮最终 Markdown 报告并结束执行。子 agent 必须提交，主 agent 可选。

cursor 是当前主会话整个 Monitor 的版本号，不是第几个 agent，也不是单个资源的编号。一个调用只接收一个 cursor，但它覆盖该 Monitor 内全部已登记资源和 kind；不同主会话使用不同 Monitor，当前不提供跨主会话查询。无 cursor（包括传 timeout）均立即返回全部未删除资源快照；带 cursor 返回该版本之后变化资源的最新状态。

watch 只返回状态、路径及失败原因，不返回报告正文。用现有 read_file 读取 result_path；是否汇总、是否继续工作、是否等待由 LLM 决定。
游标是每个调用者的位置，不表示领取或消费报告。网页与模型查询互不影响；一次增量返回每个变化资源的最新状态，可合并短时间内的多次更新。删除以 deleted 标记返回，首次快照不包含已删除资源。

每个主 session 的状态保存在 watch.json。通用 Monitor 只负责版本、资源快照和条件变量通知，不依赖 agent、模型或网页。新增 Bash 等资源只需接入 update，无需改变 watch 协议；本版本尚未增加后台 Bash 工具。
SessionRegistry 负责会话查找、创建子任务以及 agent 状态适配；SessionRuntime 管理单个 session 的 state、串行执行和取消；AgentRuntime 运行模型和工具循环。

子 Agent 普通文本结束却没有 submit 时，workflow/completion.py 根据 state.role 决定是否补交：尚未提醒且总轮数还有余量时，原 AgentRuntime 加入一次内部提醒并继续同一任务；仍未提交则失败。提醒次数记录在 execution，不另建 session，不由主 Agent 或总结模型代交，且仍受 max_rounds 总预算限制。completion.reminded 事件用于重建模型上下文，不产生新的用户消息或 turn.started；通过完成规则后才发 turn.completed。异常和主动取消不会触发补交。

子任务完成不会启动主 agent 或修改主对话。主 agent 仅在需要相关后台任务的进展或结果时调用 watch，也可在当前执行中显式等待。普通问候和无需工具的问题直接回复，不强制每条用户消息查询；没有相关任务时不重复查询或等待。主回复结束、停止或网页断开均不取消子任务；停止 watch 等待只取消当前主执行。
网页顶部主／子 agent 导航末尾显示后台任务数量，不提供手动交付按钮；后台结果由 LLM 通过 watch 查询、按需读取。
子 agent 较多或空间不足时收进下拉选择框，后台任务标识保持可见。子 session 从顶部导航查看，不出现在左侧主会话历史列表，记录仍保存在各自 session 中。

报告保存为 storage/sessions/<id>/reports/<run_id>.md。show_image 回执提供稳定的 /api/sessions/.../images/.../content 地址；submit 会规范化本轮已展示图片的路径，并补全遗漏的图片引用。报告中的 image_file 注释保留本地路径，供 read_image 使用，网页不渲染这些注释。
框架不额外运行总结模型。主 agent 可以总结或直接使用子报告中的文字和图片；图片实际内容只有显式读图时才进入视觉模型。
主 agent 的 submit 会将本轮此前的过程默认折叠到“用时”栏，默认只展示完整、可独立阅读的最终报告；展开后过程与报告连续展示。
普通问答、澄清和进度说明直接回复。复杂任务需要收起较长的分析和工具过程、呈现整理后的结论时再使用 submit，不按答案字数机械决定。
submit 会结束本轮，应单独调用。普通回复保持原样；每条用户消息开始新一轮，不合并后台自动回复。

服务重启后恢复已保存的监控状态和报告，未完成的子 agent 标为 failed，不自动重跑。CLI 一次性调用会等待后台子任务结束再退出；交互式 CLI 退出会结束其进程内任务。不要从 CLI 和 Web 同时写同一个 session。
不同 session 可并发，但模型服务器的并发容量仍然生效。同一 Moldflow study 的仿真需要保持串行。
