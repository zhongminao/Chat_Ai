# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：只产出**规划文档**（测试策略/QA 计划/issue 清单），不写测试代码、不运行测试、不装依赖。
- 上游输出路径 `/docs/ways-of-work/plan/...` 不写入；规划内容在对话中给出。
- 与已有技能分工：
  - `jeffallan-claude-skills__test-master`：测试策略 + 实际写测试；本技能只做项目层级测试规划与 issue 拆分。
  - `github-awesome-copilot__test-gap-audit`：审计已有测试缺口；本技能是从需求出发制定测试计划。
- Playwright 测试 issue 模板只是模板文本，不执行 Playwright。
