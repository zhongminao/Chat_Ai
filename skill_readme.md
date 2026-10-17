# Skill 发现与渐进式加载方案

本文记录 chat_ai 的拟议方案，尚未实现技能加载机制；不是发给模型执行的 SKILL.md。

## 职责与入口

- 框架从 config.yaml 配置的本地技能目录扫描 SKILL.md，提取名称、用途描述和文件路径。
- 独立技能模块负责发现、元数据校验与目录生成；无效技能给出诊断，不阻塞普通对话。
- 主子 Agent 都获得简短目录，由模型判断任务适用的技能；用户也可明确指定。
- 第一版复用 read_file 读取技能，不增加推荐 Agent、向量数据库或多余装配层。
- 执行、消息状态、事件持久化、停止与审批沿用现有模块；技能不自行授予权限。

## 三层披露

| 层级 | 提供的内容 | 进入模型上下文的时机 |
| --- | --- | --- |
| 目录 | 名称、描述、SKILL.md 路径 | 模型请求前提供可用目录 |
| 流程 | 选中技能的 SKILL.md 正文 | 用户指定或模型选择后 |
| 资源 | 参考资料、示例、模板、脚本执行结果 | 当前步骤确实需要时 |

描述说明“解决什么任务、何时使用、适用边界”；正文说明执行步骤和验收标准。
正文保留完成基本任务所必需的流程，附属资料只承接条件分支和详细参考，不把关键步骤藏到深层引用。
从 SKILL.md 直接链接附属资料，并明确读取条件；相对路径以技能目录为基准解析。
读取工具存在输出截断时，应继续读取余下部分，不能把文件预览视为已完整加载。
确定性的提取、转换和校验适合脚本；说明参数、输出和失败处理，通常无需先读取源码。
脚本通过现有命令工具执行，遵守相同审批、超时与停止规则。

## 网页调研示例

```text
web-research/
├── SKILL.md
└── references/
    ├── query-strategies.md
    └── source-verification.md
```

SKILL.md 保留基本流程：确认对象与完整名称 → 搜索 → 筛选相关链接 → 读取网页正文 → 交叉核验 → 附来源链接。
其中使用实际注册的 mcp_web_search 搜索，使用 mcp_web_fetch_url(url) 读取结果链接；搜索摘要主要用于筛选来源。
结果不相关时读取 query-strategies.md，学习简称扩展、地点限定、线索拆分和检索词调整。
来源冲突或数字不一致时读取 source-verification.md，区分原始来源、转述、观点和推测。
搜索引擎限流、验证码及网页正文提取质量由对应工具处理；技能指导识别受限状态和替代路径。

## 持久化与上下文整理

技能读取结果沿用现有工具消息与事件落盘，重开会话恢复当时实际读取的内容。
避免在内容仍存在于请求上下文时重复注入；渐进式加载不会自动释放已经读取的内容。
上下文整理需保留当前任务仍依赖的技能规则和引用；已结束任务的技能不必永久保留全文。
如果以后增加自动重新加载，需明确版本变化及落盘顺序，不静默替换历史上已加载的内容。

## 后续扩展与验证

目录明显占用上下文时，再增加 search_skills(query)，先返回候选元数据，再按需读取正文。
需要统一追踪加载状态、资源目录和版本时，再考虑 load_skill(name)；不要求第一版增加。
用户明确选中技能时，可在模型请求前直接加载；技能与工具定义联合延迟加载留待工具规模增长后评估。
用相同任务分别验证本地 30B 和 DeepSeek：是否选对技能、按条件读取资料、获取正文、核验并提供来源，以及停止和整理后能否继续。

## 访问模式边界

full_access 跳过 chat_ai 后端的逐次工具审批；其他 MCP 的限制由对应服务端决定。
本地 write_file/edit_file 仍校验目标在 workspace 内；read_file 可读取 workspace 外、运行账户有权限的路径。
run_bash 仅设置工作目录，没有路径沙箱，脚本可访问运行账户有权限的其他路径；执行仍受超时和停止控制。
Windows RemoteWindowsMCP 的 root 仅作为默认路径，不限制跨目录的文件、图片和命令 cwd。全部 MCP 调用由 chat_ai 后端 ApprovalGate 决定是否需要批准；Windows MCP 不重复实现审批模式，执行仍受 Windows 账户权限限制。
MCP 只调用已成功注册的工具；其他客户端直接连接 Windows MCP 时不经过 chat_ai 审批。

## 参考

- [Agent Skills：客户端集成与上下文管理](https://agentskills.io/client-implementation/adding-skills-support)
- [Anthropic：技能组织与条件披露](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Anthropic：资源和脚本的按需使用](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Deep Agents：用户指定加载、工具绑定与刷新](https://www.langchain.com/blog/revamping-skills-in-deep-agents)
