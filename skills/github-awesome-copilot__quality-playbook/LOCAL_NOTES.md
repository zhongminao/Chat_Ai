# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/*`、`phase_prompts/*`、`agents/*`、`quality_gate.py`、`LICENSE.txt`(Apache-2.0, 作者 Andrew Stellman)、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`：上游要求**写** `quality/` 目录产物、运行 `python3 -m bin.run_playbook`（Mode B 会派生 CLI 子代理）、执行 `quality_gate.py` 与 `phase_prompts` 流程；本环境**均未执行/未验证**，也未安装任何依赖。
- 接入后可用形态：以 Mode A（skill-direct）思路，逐阶段读取 `phase_prompts/phaseN.md` 与 `references/*` 做**对话内**分析，产物（EXPLORATION/需求/评审/bug 清单）作为回答文本输出，由用户决定落盘；不含 bin/ 运行器。
- 这是重量级技能：一次“完整运行”代价很高，应显式询问用户范围（全仓/单模块）与是否按阶段推进。
- 与 `code-reviewer`（单个 PR 审查）、`test-gap-audit`、`security-review` 区分：本技能是**端到端质量体系审计**。
