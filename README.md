# chat_ai

## 开发约定

代码保持简洁，模块职责清晰，功能通过小模块组合。CLI、Web 和核心控制器共用事件流；界面逻辑不进入核心。文档只记录真实行为和必要入口。

## 当前结构

```text
agent/core/       AgentRuntime、状态转移和工具调度
agent/model/      模型协议、provider、模型目录、图文消息组装
agent/tools/      本地工具、schema、router、spill
agent/tools/mcp/  MCP 客户端与 adapter
agent/storage/    session、events.jsonl、图片与缩略图
agent/workflow/   配置、AgentState、HistoryNode、共用输入与命令
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

Web 前端使用 React + TypeScript + Vite，源码位于 `agent/web/frontend/`。
首次启动 Web 前先构建前端（需要 Node.js 20.19+ 或 22.12+）：

```bash
cd agent/web/frontend
npm ci
npm run build
```

生产访问 `http://127.0.0.1:8764`；FastAPI 提供 `dist/index.html`、`/assets` 和原有 `/api`。
8764 是网页服务端口，模型仍由 provider 配置选择，可直接使用 DeepSeek API。

前端开发时保持上述 FastAPI 服务运行，在另一个终端执行：

```bash
cd /home/zhong/mydisk/tools/chat_ai/agent/web/frontend
npm run dev
```

访问 `http://127.0.0.1:5173`，Vite 将 `/api` 代理到 `127.0.0.1:8764`。
前端检查：`npm test`；`npm run build` 包含 TypeScript 检查。

修改 Python 后端或 provider 适配代码后，需要重启 uvicorn；修改前端后需要重新构建并刷新页面。
8764 是 chat_ai 网页服务端口；8002 是本地千问的模型服务端口，两者独立启动。

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
点击新会话时优先复用没有消息且未运行的空会话，找不到才创建；
是否为空通过原有 conversation 接口确认，连续点击不会反复创建空记录。
纯文本调用与旧事件兼容，图片引用通过同一消息和事件流程处理。

## 会话名称

Web 会话列表中的铅笔按钮可修改名称；按 Enter 或点击勾号保存，Esc 或取消按钮放弃修改。
保存后列表和当前对话页眉一起更新。名称需要 1–80 个字符，前后空白会被移除，不能包含换行或控制字符。
CLI 在当前会话中输入 `/rename 图片识别实验`，也可以修改同一个名称。

Web 的 `PATCH /api/sessions/{id}` 接收 `{"title":"新名称"}`，与 CLI 共用
`agent/storage/session.py` 的 `SessionStore.rename(session_id, title)`，统一校验并原子写入 `session.json`。
自定义标题保存在会话元数据中；没有自定义标题的旧会话继续根据首条消息生成名称。
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

CLI 和 Web 共用根目录 `config.yaml` 的运行配置：

```yaml
max_rounds: 200
system_prompt: |
  You are a small coding assistant. Use the provided tools when needed.
  Workspace directory: {workspace}
```

主 Agent 每次用户请求、子 Agent 每次委派任务各自最多执行 `max_rounds` 轮模型调用，默认均为 200；一轮可包含多个工具调用。
子 Agent 继承主 Agent 的轮数上限和系统提示词，不再另设 4 轮限制。达到上限会结束该任务并报错。
`max_rounds` 必须为正整数；`system_prompt` 必须为非空文本。实际默认提示词还包含图片工具的使用规则，修改时可直接编辑 YAML 多行文本。
提示词中的 `{workspace}` 替换为实际工作区绝对路径，其他花括号原样保留，支持直接写入 JSON 示例。
配置在创建 Agent 时加载；修改后重启 Web 和 CLI，即可让新旧会话使用最新配置，不改写历史日志。

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
agent/model/messages.py     图片说明与模型消息组装
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
子 agent 的图片保存在它自己的 session，可从顶部子 agent 导航查看。父级只接收 submit 的最终报告；报告可附上图片的完整路径。

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

实现入口：`agent/tools/images.py`、`agent/tools/result.py`；消息组装位于 `agent/model/messages.py`，
能力配置读取位于 `agent/model/catalog.py`，历史恢复位于 `agent/workflow/history.py`。

## 模型配置与本地服务

模型目录位于 `agent/model/providers/providers.yaml`，Web 和 CLI 共用该配置。

| Provider | 当前用途 | 接口 |
| --- | --- | --- |
| `deepseek` | 默认模型 `deepseek-flash` | DeepSeek API |
| `gpt` | GPT 模型选择 | passion8 网关 |
| `local-qwen3p5-9b` | 本地千问 9B，图片识别 | `http://127.0.0.1:8002/v1` |

远程模型 API 密钥由 provider 配置中的 `api_key_env` 指定，例如 `DEEPSEEK_API_KEY`、`GPT_API_KEY`。
测试图片时，在模型选择器中切换到本地 `local-qwen3p5-9b`。
图文请求使用共用的 `agent/model/messages.py`；本地 Qwen 适配位于 `agent/model/providers/qwen.py`。
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

搜索桥接请求本地 SearXNG 时保持直连；`fetch_url` 读取 HTTP_PROXY/HTTPS_PROXY 等环境变量访问外部网页。
使用终端代理时同时设置 `NO_PROXY` 和 `no_proxy` 为 `localhost,127.0.0.1,::1`，避免本地 MCP 和模型接口绕到代理。
当前用户服务的固定代理配置位于 `~/.config/systemd/user/chat-search-mcp.service.d/20-proxy.conf`；终端的 `proxy_on`/`proxy_off` 不会修改已运行服务的环境。修改服务配置后执行 `systemctl --user daemon-reload` 并重启 `chat-search-mcp.service`。

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

先保持检索模块独立，不把索引、向量库和排序逻辑放进 `AgentRuntime`。具体数据源、向量模型和存储方式在实现前单独确定。


## 独立子 agent 与最终报告

`AgentRuntime` 执行一次模型/工具循环；`SessionRuntime` 管理 session 的串行队列、停止、报告和父子通知。
Web 与 CLI 共用这两层。每个 session 有自己的运行线程、历史、图片和取消信号，不同 session 可并发执行。

主 agent 调用 `delegate(system_prompt, user_prompt)`，立即取得子 session ID。子 agent 使用这两个提示词、创建时主 agent 的模型和共享工作区，不复制主对话或图片。子 agent 不注册 delegate，必须调用一次 `submit(content)` 提交完整报告；普通文字结束不算成功提交。

主 agent 也有 submit，用于可选的正式报告。submit 结束本次执行，不关闭主 session。成功提交后的同批其他工具调用会被跳过。
网页在 submit 后将最近一条用户消息到本次提交之间的执行过程折叠，折叠栏显示用时（包含等待子任务的时间），最终 Markdown 正文始终显示；展开可查看过程文字、工具调用和图片。子 agent 回传报告只供主 agent 读取，不在主对话渲染。子 session 供查看和停止，后续任务应创建新的子 session。

子任务结束后，SessionRuntime 将唯一报告或失败状态送入父 session 的队列；父 session 当前回复结束后再处理。
内部报告采用独立事件/消息类型，模型适配器将其转换为带来源标识的观察消息，不冒充真实用户，也不补写已完成的 delegate 工具回执。
父 agent 空闲时自动处理报告；主动停止后只接收保存，直到你发送下一条消息才继续执行。关闭网页、切换会话、结束回复或停止父回复都不会取消子任务。

顶部可切换主/子 agent，连接状态移至输入框下方。删除主 session 前需要先删除它的子 session，运行中的 session 不能删除。
任务由 chat_ai 服务进程维护；重启服务会中断尚未完成的任务，不会自动重跑。父 session 再次载入时补收已提交报告或中断状态，按子 session ID 去重。
CLI 一次性请求会等待子任务和报告处理完毕再退出。不要同时用 CLI 与 Web 写入同一个 session。
模型服务自身的并发限制仍然生效；共用同一个 Moldflow study 的仿真仍应串行执行。
