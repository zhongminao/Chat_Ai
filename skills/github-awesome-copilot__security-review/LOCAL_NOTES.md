# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/*`（language-patterns、vuln-categories、secret-patterns、vulnerable-packages、report-format）、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`：**不联网**查询 CVE 库、不运行 `npm audit`/`pip-audit`；`references/vulnerable-packages.md` 只是离线名单，需提示用户自行核对最新 CVE。脚本/补丁均不自动应用（上游也要求人工确认）。
- 与已有技能分工（同类项无法合并，但上下文与产物可区分）：
  - `jeffallan-claude-skills__code-reviewer`：通用 PR/差异评审（bug、性能、可维护性），本项目已在其 `excludes` 里划出安全审计。
  - `openai-skills__security-best-practices`：写**默认安全**代码 + 最佳实践；`openai-skills__security-threat-model`：威胁建模（信任边界/滥用路径）。本技能是**代码级数据流漏洞扫描**，不写安全方案、不做威胁建模。
- 报告默认在对话输出；用户要求落盘需另行授权。
