# chat_ai 交接

生产代码保持简洁模块化，以清晰边界和可维护性为目标，合理的代码增量可以接受；测试代码增量不限制生产设计。CLI 与 Web 共用运行层和事件协议。

## 核心边界

- agent/core/agent_runtime.py：一次模型与工具循环；submit 结束本轮。
- agent/core/agent_factory.py：构建 state、按 role 选择配置提示词、注册工具并装配 AgentRuntime。
- agent/core/session_runtime.py：独立持有 session state，管理执行队列、停止、模型切换命令、报告落盘和 worker 退出时模型资源清理。
- agent/core/session_registry.py：会话创建/查找、子 agent 启动与监控状态适配。
- agent/core/monitor.py：通用资源快照、增量游标、条件变量等待；不调用模型，不操作对话。
- agent/storage/reports.py：保存报告，规范化已展示图片的 Markdown 引用。
- agent/storage/database.py：SQLite 版本检查、WAL、复用连接与短事务锁，按 durable 切换 NORMAL/FULL；session.py 的 list_summaries() 直接查询会话摘要，不读取事件正文。
- agent/storage/event_log.py：SQLite 有序事件；同一事务分配会话 seq、写事件与更新摘要，提交成功后发布；images.py 管理 SQLite 图片元数据及磁盘文件。
- agent/web/events.py：SSE 初始化、历史边界与实时队列衔接、游标续传和缺口补读；只负责传输，不写业务事件。前端 api/events.ts 接收控制消息，state/conversation.ts 在 ready 后开放输入。
- agent/tools/router.py：统一工具路由；执行受控工具前调用共享审批入口。
- agent/tools/approval.py：规则、待审批状态、一次性决定与可取消等待。SessionRuntime 持有主子共用的实例，factory 注入；不放入 AgentState。
- agent/workflow/transitions.py：简单状态节点与流程路由；节点只返回 StateUpdate。
- agent/workflow/message_updates.py：消息状态变更；agent/workflow/message_replay.py 的 restore_display_messages 从事件重建消息。
- agent/workflow/context_compaction.py：独立的整理状态更新规则；model/tokens.py 的 count_request_tokens 统计请求大小，model/context_summary.py 执行无工具摘要请求。Runtime 在每次模型请求前检查，先记录 context.compacted 的完整 messages，再 apply。
- agent/model/catalog.py：模型目录与 get_binding；只复用当前目标的资源，替换时关闭旧资源，连接不进入 state。
- agent/model/http_client.py 的 ModelHttpClient：复用模型 HTTP 连接，内部异步网络请求适配同步模型流；取消覆盖请求建立和流读取，关闭本次请求并等待本地清理后由运行时发 turn.cancelled；不确认模型端是否停止。
- agent/workflow/completion.py：根据 role 和 execution 判断正常结束、一次补交提醒或失败，不操作会话或执行 I/O。
- /home/zhong/mydisk/services/web-mcp/web.py：独立 Docker Web MCP 服务；agent/tools/mcp/client.py 的 McpClient 负责连接与调用。SearXNG 在 services/searxng；两组 Compose 的网络策略复用 services/web-mcp/network-policy.sh，业务进程无 NET_ADMIN，启动门禁确保规则就绪。公网直连，不使用旧局域网代理；默认搜索为必应（cn.bing.com）、搜狗、360。旧 agent/mcp_servers 与 chat-search-mcp 用户服务已移除，入口端口不变。

config.yaml 的 storage_dir 指定根目录；chat_ai.sqlite3 保存 sessions、events、images、monitors，sessions/<id>/ 只保存附件和 Markdown 报告。保留现有 SQLite 会话，不迁移或清空数据，不保留 JSONL／JSON 存储分支；图片 ID、URL、磁盘路径和事件回放协议不变。chat_ai 使用独立 conda chat-ai-py313（Python 3.13.2，SQLite >=3.51.3）与标准库 sqlite3，无 ORM／额外服务；原 py313 及模型服务环境保持不变。WAL+NORMAL 用于流式片段，完成、取消及其他关键事件仍 FULL，所有事件提交后才发布，不增加后台写入队列。每个 Database 持有一条跨线程复用、锁保护的连接，保留默认自动检查点；NORMAL 不保证断电前最近事务已持久化。备份方式见 README，不能运行时仅复制主数据库文件。通用协议适配为 model/openai_compatible.py 的 OpenAICompatibleAdapter；QwenChatTemplateAdapter 只负责 Qwen 模板选项。

AgentState 保存 role（main/child）、model、messages、execution；运行时应用节点更新并执行 I/O。不保存 state checkpoint。

## 运行中引导

core/steering.py 管理已提交、不可修改的引导消息，SessionRuntime 持有并用同一锁协调接收与结束；AgentRuntime 在完整工具组之后、最终回复/submit 结束前检查，先记 guidance.applied 再调用 message_updates 更新 messages。queued/applied/undelivered 分别表示接收、加入上下文、未交付；停止和重启不自动续跑未交付消息。消息恢复与上下文整理保留已交付引导及完整工具组。
Web 运行时回车只进本标签页 sessionStorage 中按会话隔离的前端队列；点击任意一条引导才调用 /guidance。编辑撤回输入框，重发排队尾；发送后不可修改并按普通消息展示，不显示引导状态标记；原助手块仍在其上方更新。执行指示位于首条未交付引导之前，交付后移到其后。输入区单按钮按空闲／运行及输入内容切换发送、入队和停止。CLI 交互模式持续接收输入并直接调用 SessionRuntime.send，不再等待整个任务结束；审批用命令处理，一次性 CLI 保留原审批等待流程。子会话仍只供查看。未增加暂停或工具取消机制。

## 自动上下文整理

config.yaml 的 context 配置只保留开启、触发 110592（108K）和独立提示词文件；不再设固定目标或摘要输出上限，提示词不设字数。
生产提示词集中在 prompts/：main_agent.md、child_agent.md、context_compaction.md；config.yaml 只保存文件路径，操作说明在 README；不加载 SKILL.md，也不向摘要模型传脚本说明。
用户输入、完整工具组和补交提醒均在下一次业务模型请求前统一检查，主子 Agent、CLI/Web 共用入口。
整理保留系统提示词、最新用户原文及最后完整助手／工具组；摘要由当前模型参与，不由脚本替代语义整理。
30B 使用 llama.cpp 实际模板计数；其他 provider 暂估算（UTF-8 字节 / 3，加每张图片 4096），包括工具 schema，不保证视觉硬上限。
模型按当前任务所需信息决定摘要详略；框架只检查非空、确实缩小且回到触发线以下，模型服务自身窗口／输出限制仍有效。
摘要失败、截断、未缩小、仍达到触发阈值或提交前取消保留原 messages；成功先持久化再更新内存，不循环重试，不新建 session。
message_replay.restore_model_messages 恢复最新整理结果并回放后续事件；网页历史由前端 reducer 从 SSE 事件恢复，restore_display_messages 保留给只读 Notebook 和历史校验。
配置不变时恢复确定消息；显式修改配置仍更新角色系统提示词，不重新摘要。
context.compaction.started / context.compacted / context.compaction.failed / context.compaction.cancelled 是共享反馈。
Web 显示整理中及持久完成标识，submit 折叠后也可见；CLI 输出文字。旧跨会话交接实验脚本、专用测试和 README 已删除，仅保留 agent 中的生产整理模块。

## 子 agent / watch

主 agent 有 delegate(user_prompt)、watch(cursor=None,timeout=0)、submit(content)；子 agent 有 submit，没有 delegate/watch。
主、子完整系统提示词分别为 prompts/main_agent.md、prompts/child_agent.md，由 config.yaml 的 system_prompt_file、child_system_prompt_file 指定；路径相对配置目录解析，内容须为非空 UTF-8。Config 仍向 factory 提供已读取的提示词文本；旧元数据 system_prompt 不覆盖配置。
delegate 立即返回独立 session ID 和 watch 使用提示。cursor 是当前主会话整个 Monitor 的版本号，不是 agent 编号；一个 cursor 覆盖其全部资源和 kind。watch 无 cursor 立即返回快照，有 cursor 为增量，timeout>0 等待任意变化；返回状态和 result_path，正文由 read_file 获取。每个调用者自行保存游标，无领取状态。
监控状态由 SessionStore 读写 SQLite monitors 表；Monitor 保留内存快照、版本及条件变量等待。未来可登记其他 kind，例如后台 Bash；当前只实现 agent 生产者。
子任务完成只更新监控状态，不启动父模型，不写父消息。新的用户消息才开始新一轮；正在等待的 watch 可被变化唤醒。
主 agent 仅在任务需要时使用 delegate/watch；问候直接回答，无相关后台任务时不循环查询。会话列表在 turn.started 后刷新首条消息标题，自定义标题仍优先。
网页选中 ID 由 features/sessions/useSessions.ts 存入本标签页 sessionStorage（chat-ai:selected-session）；刷新恢复当前会话，新标签页默认空会话，保存的会话已删除或主动删除当前会话时回到空会话。只按摘要核对 ID，恢复时不读取其他历史；存储不可用不阻塞使用。浏览器恢复／复制标签页可能保留原状态。空会话复用仅重新查询摘要校验，不加载正文，选中后后台刷新列表。

会话下行统一到 /api/sessions/{id}/events，旧 /conversation 快照接口、ConversationSnapshot 和前端请求已删除。每次连接先发 session.init（模型、图片、父会话、busy、历史边界 seq、续传 after、必要时 reset），回放该边界内缺失事件后发 session.ready，再接实时队列；控制消息不落盘，不创建 Agent/MCP。先订阅队列再读历史，双方按 seq 去重，服务端遇到跳号先读 SQLite 补齐。init 的 SSE id 是续传起点而非边界，ready 不推进 id；避免半途断线跳过尚未接收历史。
前端保留断线前消息，连接中断即禁用输入，重连按 Last-Event-ID 补读并刷新初始化状态，ready 后重新开放；即使无新事件，服务重启后的旧 running 状态也会被纠正。游标超前时 reset 清空前端旧投影并完整回放，负数／格式错误返回 HTTP 错误。发送、停止、审批等命令仍走原 HTTP 接口。
不同 session 可并发，停止父回复不停止子任务；服务重启不自动重跑中断任务。
停止只负责标准本地取消、关闭网络流并通知 Web；清理期间显示“正在停止”，不检查模型服务端生成资源。

## 报告与图像

submit 保存 reports/<run_id>.md 并发出 report.submitted 事件，子任务进入 completed。
子 agent 普通文本结束但未 submit 时，在 max_rounds 预算内最多提醒一次，由原子 agent 在同一执行中提交；仍未提交则失败。completion_reminders 在 execution 中，completion.reminded 事件恢复内部提醒，不新增用户轮次，也不先发完成再判失败。
show_image 返回图片的稳定网页地址；报告保存时补全已展示图片，image_file HTML 注释提供模型读图所需的本地路径，网页忽略注释。
不额外运行报告总结 agent。主 agent 自主读取、判断、汇总或直接引用报告。
网页顶部主/子导航末尾显示后台状态，子 agent 过多时折叠到下拉框，不提供手动交付按钮；保留输入框下连接状态和 submit 折叠过程。原始子报告不注入主对话。

## 服务

KVM 虚拟机已部署 /home/zhong/chat_ai，使用虚拟机用户级 chat_ai.service，监听 127.0.0.1:8200，enabled 且 zhong linger=yes。独立离线 Python 3.13.2/SQLite 3.53.4 在 ~/.local/share/chat-ai-py313；运行配置 ~/.config/chat_ai/config.yaml 由 CHAT_AI_CONFIG 指定，显式 load(path) 优先于环境变量，未指定时仍用项目默认配置。当前仅本地 30B 网关 192.168.250.1:18081 与 Web MCP 127.0.0.1:8766，不复制云 API 密钥。虚拟机默认代理 http://127.0.0.1:17897，由宿主机用户服务 chat-ai-vm-proxy 经 SSH 转到 Windows 10.23.13.164:17897。虚拟机 ~/.config/chat_ai/proxy.env 同时供 .bashrc 的 proxy_on/proxy_off 和 chat_ai 用户服务 proxy.conf 使用；NO_PROXY 保留本机 MCP 与模型网关直连，不放开原有网络过滤规则。宿主机 push_to_vm.py 已被 Git 忽略，同步项目但排除忽略项及脚本自身；dist 需单独传。登录、管理、VS Code 端口转发步骤见 README。

项目 /home/zhong/mydisk/tools/chat_ai，systemctl --user chat_ai，Web 8200；用户 unit 的 ExecStart 使用 /home/zhong/mydisk/miniconda3/envs/chat-ai-py313/bin/python。修改 unit 后执行 systemctl --user daemon-reload 并重启，确认实际进程使用新环境；模型服务不切换环境。
MCP：remote_windows http://127.0.0.1:8767/mcp；web http://127.0.0.1:8766/mcp（mcp_web_search / mcp_web_fetch_url）。
McpClient 按服务发现工具，单服务连接／初始化／发现合计超时 1 秒；失败记录告警，只跳过该服务工具，不阻塞普通对话、本地工具和其他 MCP。调用期间断开仍返回工具错误。不加后台重试；恢复后新建会话或重启应用重新发现。
ToolRouter 只执行本轮已注册的工具；旧 MCP 工具或其他未注册工具返回“当前工具不可用”的工具回执，继续后续工具与模型循环，不改写历史。
DEEPSEEK_API_KEY 和 GPT_API_KEY 均由 ~/.config/chat_ai/chat.env 提供，修改后重启服务，不在仓库中保存；仅配置 .bashrc 不会让 systemd 自动继承。
GPT 默认 gpt-6-sol，保留原模型 ID 以便历史切换；2026-10-16 网关的 gpt-5.5 返回 503 无通道。providers/gpt.py 的 GPTChatAdapter 按型号传 Chat Completions reasoning_effort：gpt-6-astra 为 low，其余当前 GPT 型号为 none；Qwen 与 DeepSeek 请求不受影响。

## 工具审批

config.yaml 的 approval.mode 默认 audit；可切换 full_access。受控范围是本地 write_file/edit_file/run_bash 与所有已注册 MCP 工具，包括 MCP 读取。批准绑定当次工具参数副本；拒绝回工具回执，停止唤醒等待且执行前再次检查取消。主子 Agent 共用规则、模式和待审批列表；根会话事件记录 requested/resolved/bypassed/mode.changed，带来源 sessionId/runId/callId。SQLite 事务保护跨线程／进程事件序号，EventLog 在提交后通知；FULL 用于关键事件，NORMAL 用于流式增量。
Web 输入区左侧模式切换，模型位于发送左侧；features/approvals 每秒读取运行时快照，主页面显示子任务请求，刷新可继续审批，卡片支持批准本次/拒绝本次/停止来源任务。CLI approval.py 在主线程处理输入，支持 --access、/access、/approvals、/approve、/reject、/stop。待审批时禁止切换模式。切换模式落事件，重开恢复；服务重启后旧请求失效，不恢复许可、不重跑任务。

技能发现与渐进式加载的待实现方案见 skill_readme.md。Windows RemoteWindowsMCP 源码在 D:/local_mcp；root 仅为路径起点，跨目录访问不再被固定根目录拦截。MCP 权限统一由 chat_ai 后端 ApprovalGate 控制，Windows 端不重复审批；直接连接 MCP 的其他客户端不经过此审批。
