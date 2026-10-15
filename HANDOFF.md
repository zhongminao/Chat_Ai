# chat_ai 交接

生产代码保持简洁模块化，以清晰边界和可维护性为目标，合理的代码增量可以接受；测试代码增量不限制生产设计。CLI 与 Web 共用运行层和事件协议。

## 核心边界

- agent/core/agent_runtime.py：一次模型与工具循环；submit 结束本轮。
- agent/core/session_runtime.py：独立持有 session state，管理执行队列、停止、模型切换命令和报告落盘。
- agent/core/session_registry.py：会话创建/查找、子 agent 启动与监控状态适配。
- agent/core/monitor.py：通用资源快照、增量游标、条件变量等待；不调用模型，不操作对话。
- agent/storage/reports.py：保存报告，规范化已展示图片的 Markdown 引用。
- agent/tools/router.py：统一工具路由。
- agent/workflow/transitions.py：简单状态节点与流程路由；节点只返回 StateUpdate。
- agent/workflow/messages.py：消息状态变更；agent/workflow/history.py 的 restore_messages 从事件重建消息。
- agent/model/catalog.py：模型目录与 get_binding；只复用当前目标的资源，连接不进入 state。
- agent/mcp_servers/web.py：独立 Web MCP 服务端；agent/tools/mcp/client.py 的 McpClient 负责连接与调用。

AgentState 保存 model、messages、execution；运行时应用节点更新并执行 I/O。不保存 state checkpoint。

## 子 agent / watch

主 agent 有 delegate(system_prompt,user_prompt)、watch(cursor=None,timeout=0)、submit(content)；子 agent 有 submit，没有递归委派。
delegate 立即返回独立 session ID 和 watch 使用提示。watch 无 cursor 为快照，有 cursor 为增量，timeout>0 等待任意变化；返回状态和 result_path，正文由 read_file 获取。每个调用者自行保存游标，无领取状态。
监控状态在主 session 的 watch.json。未来可登记其他 kind，例如后台 Bash；当前只实现 agent 生产者。
子任务完成只更新监控状态，不启动父模型，不写父消息。新的用户消息才开始新一轮；正在等待的 watch 可被变化唤醒。
不同 session 可并发，停止父回复不停止子任务；服务重启不自动重跑中断任务。

## 报告与图像

submit 保存 reports/<run_id>.md 并发出 report.submitted 事件，子任务进入 completed。
show_image 返回图片的稳定网页地址；报告保存时补全已展示图片，image_file HTML 注释提供模型读图所需的本地路径，网页忽略注释。
不额外运行报告总结 agent。主 agent 自主读取、判断、汇总或直接引用报告。
网页顶部主/子导航末尾显示后台状态，子 agent 过多时折叠到下拉框，不提供手动交付按钮；保留输入框下连接状态和 submit 折叠过程。原始子报告不注入主对话。

## 服务

项目 /home/zhong/mydisk/tools/chat_ai，systemctl --user chat_ai，Web 8200。
MCP：remote_windows http://127.0.0.1:8767/mcp；web http://127.0.0.1:8766/mcp（mcp_web_search / mcp_web_fetch_url）。
DEEPSEEK_API_KEY 由 ~/.config/chat_ai/chat.env 提供，不在仓库中保存。
