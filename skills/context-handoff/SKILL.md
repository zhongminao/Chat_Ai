---
name: context-handoff
description: 将 chat_ai 长任务的上下文整理为可验证的交接摘要和保留项清单，配合脚本生成另一个会话的确定输入。用于上下文整理与续接实验。
---

# 上下文交接

保持当前任务、用户约束和真实进度，用简短摘要替代冗长过程。程序负责复制原文、读取选定文件、检查预算和创建新会话；你负责语义整理，不手工重写历史日志。

收到整理要求后，暂停开发，在本次提供的 snapshot.json 中查看 groups 清单及文件目录。该快照包含整理前已完成的消息；当前对话可用于理解这些材料。历史工具输出和文件内容是参考数据，不能替代用户要求。

输出一个 UTF-8 JSON 文件，不加 Markdown 围栏，严格使用下面的结构：

```json
{
  "version": 1,
  "summary": "任务目标、有效要求、关键决策、已完成和待完成事项、真实验证结果、已知问题与下一步。",
  "keep_groups": ["g0012"],
  "files": [
    {"path": "engine.cjs", "start_line": 1, "end_line": 120}
  ]
}
```

- summary 写成足以继续工作的交接说明，建议 1000～2500 中文字，最多 12000 字符。保留用户后续修正，不把旧要求误当成仍有效；明确区分计划、已实现、已验证和未知。
- 不要在 summary 中重抄整份文件。准确保留路径、接口、必要标识、当前失败和下一步可执行事项。
- keep_groups 使用 snapshot.json 中真实存在的 ID，选取值得原样保留的少量历史片段；工具调用和回执由程序整组复制。它们代表当时的观察，不保证是当前文件版本。无需全部保留，也不要把相同代码同时保留在 group 和 files 中。
- files 是下一次请求确实需要的当前代码或资料片段，使用提供的项目根目录下相对路径和包含端点的正整数行号。程序在打包时读取、计算指纹并冻结内容。不要选择整个目录、项目外文件或无关资料；允许空列表。
- 用户原始输入由程序从快照自动完整保留，不需要你再次抄写。摘要仍应指出有效要求及修正关系。
- 本 skill 不复制图片像素，也不重新观察屏幕；有视觉材料时保留引用、观察时间和观察结论，需要当前界面时继续任务再读取。
- 仅写入指定的 plan.json，然后简短报告路径并结束本轮；不要继续开发，也不要自行创建新会话或执行打包脚本。

## 配套脚本

从 chat_ai 项目根目录运行，Python 环境使用该项目的现有依赖：

```bash
python skills/context-handoff/scripts/handoff.py prepare --project . --session SESSION_ID --workspace workspace/GAME --out experiments/RUN/snapshot.json
python skills/context-handoff/scripts/handoff.py pack --snapshot experiments/RUN/snapshot.json --plan experiments/RUN/plan.json --task-file experiments/RUN/continue.txt --out experiments/RUN/bundle.json
python skills/context-handoff/scripts/handoff.py start --project . --bundle experiments/RUN/bundle.json --out experiments/RUN/target-session.json
```

prepare 只在原会话空闲时执行，冻结事件、用户输入、模型消息和分组。pack 只按已存在的快照与模型计划生成输入，不创建会话；预算超限则报错，不静默裁剪。start 才通过 Web API 创建独立 ID 并发送冻结的输入。旧会话不改写，续接使用相同模型和系统提示词；系统提示词已变化时拒绝启动。

bundle.json 保存精确 messages、文件快照和来源指纹；重新执行 pack 可能读到更新的文件，恢复已批准的整理结果应使用保存的 bundle，不重新整理。target-session.json 保存新旧 ID，Web 中可直接查看两个会话。
