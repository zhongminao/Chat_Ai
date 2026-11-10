# 本地接入说明（未修改上游文件）

- `SKILL.md`、`prompts/`、`references/`、`templates/`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- 只授予 `read_file`，且**只在会话记录/日志文件已存在、用户给出路径时**才可用：
  - 上游默认读取 `~/.superpowers/<session-id>/` 目录，并**创建 case/report 目录写盘**（含 `templates/case.md`、`templates/report.md`）——本环境未授予 write_file，报告只在回复中输出，由用户自行落盘。
  - 上游第 3 步要求**并行派发 analyst 子代理**、第 5 步用 `gh` 查/建 issue、第 6 步导出 scrub bundle——均**不执行**（无子代理/gh/写盘权限，禁止联网）。改为由本 agent 按 `prompts/analyst-common.md` + 各维度文件逐个维度分析，并把 GitHub issue 文本作为建议内容给出。
  - 引用纪律保留：**每条结论必须给出 `path:line` 或用户粘贴的原文片段**；无法取证的结论只能标为“未证实推测”或不写。
- 与 `github-awesome-copilot__incident-postmortem` / `wshobson-agents__postmortem-writing`（生产事故复盘）、`bug-receipt`（缺陷结案回执）、`obra-superpowers__verification-before-completion`（完成前取证）、`doublecheck`（声明核查）区分：本技能对象是**历史 AI 会话记录**。
