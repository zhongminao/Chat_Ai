# 本地适配说明（openai-skills__define-goal）

- 上游：openai/skills（Apache-2.0，见 `LICENSE.txt`），`.curated/define-goal`，原文原字节复制；包内无脚本。
- 仅授予 `read_file`：纯目标定义指导，不写盘、不执行命令。
- 上游步骤 5/6 要求调用 Codex 专用目标工具 `get_goal` / `create_goal`（`$define-goal` 语法）；本环境**没有这些工具**，请不要伪造调用，改为在对话中输出结构化目标文本由用户确认。
- `agents/openai.yaml` 是 Codex 界面元数据（display_name / default_prompt），仅作参考，不参与本地检索。
- 与 `github-awesome-copilot__prd`、`obra-superpowers__writing-plans` 区分：本技能只定义「目标与验收标准」，不产出需求文档或实现计划。
