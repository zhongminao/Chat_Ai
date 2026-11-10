# 本地适配说明（openai-skills__security-threat-model）

- 上游：openai/skills（Apache-2.0，见 `LICENSE.txt`），`.curated/security-threat-model`，原文原字节复制；包内无脚本。
- 仅授予 `read_file`：上游要求把最终模型写入 `<repo>-threat-model.md`，但本技能未授予 `write_file`；如需落盘请由主 agent 在用户明确要求下另用写文件能力（并在报告中注明路径），或直接输出 Markdown 文本。
- 上游要求在第 6 步「暂停等待用户确认假设」后再出最终报告；在本 agent 中应至少在首次回复中列出关键假设与待确认问题。
- 与 `jeffallan-claude-skills__code-reviewer` 区分：本技能做架构级威胁建模，不逐行审查代码；通用代码审查请用 code-reviewer。
- `agents/openai.yaml` 为 Codex 界面元数据，仅参考。
