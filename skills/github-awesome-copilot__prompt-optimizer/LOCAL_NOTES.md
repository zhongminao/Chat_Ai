# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：无外部依赖，不调用任何 LLM API。
- 与 `jeffallan-claude-skills__prompt-engineer` 分工：对方面向**提示词工程与评测框架**（模板、few-shot、chain-of-thought、system prompt guardrails、回归评测）；本技能只做**一次性把草稿变成可粘贴的 chat prompt**（禁占位符、内容内嵌）。excludes 已按此切分，避免互抢。
- 上游“输出只有代码块、不加解释”的强格式要求需遵守；用户事后问“改了什么”再解释。
