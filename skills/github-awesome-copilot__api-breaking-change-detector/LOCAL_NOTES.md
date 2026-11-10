# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能：只授予 `read_file`，靠对话中给出的 diff/文件内容做交叉核对，不执行构建、不联网、不写盘。
- 上游面向 C#（ASP.NET Core）后端 + TypeScript/JavaScript 前端；其他语言栈不适用。
- 上游提到 `references/*` 或 Word/JSON 产物均未包含在本包中；报告以对话文本输出。
- 与已有技能分工：本技能只看**接口契约漂移**，不做漏洞扫描（`security-review` 类）、不做通用代码审查（`code-reviewer`）。
