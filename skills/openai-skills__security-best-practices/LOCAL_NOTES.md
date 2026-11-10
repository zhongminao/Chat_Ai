# 本地适配说明（openai-skills__security-best-practices）

- 上游：openai/skills（Apache-2.0，见 `LICENSE.txt`），`.curated/security-best-practices`，原文原字节复制；包内无脚本。
- 仅授予 `read_file`：本技能是参考文档 + 审查指导。上游建议把报告写到 `security_best_practices_report.md`；本技能未授予 `write_file`，需要落盘时请由主 agent 在用户明确要求下另行写文件，或直接在回复中给出报告。
- 上游提到「不确定时可联网查文档」；本环境不联网，缺少框架参考时明确告知用户「无本地具体规范，仅给通用建议」。
- 覆盖范围仅 Python、JavaScript/TypeScript、Go Web 栈；Java/C#/Rust 等无对应参考。
- 与 `jeffallan-claude-skills__code-reviewer`（通用 PR 审查）、`openai-skills__security-threat-model`（架构威胁建模）区分：本技能是语言/框架级安全编码规范与安全报告。
- `agents/openai.yaml` 为 Codex 界面元数据，仅参考。
