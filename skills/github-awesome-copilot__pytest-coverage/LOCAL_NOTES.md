# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 纯指导技能，只授予 `read_file`：**不安装 pytest / pytest-cov，不运行任何测试命令**；只给出应执行的命令（`pytest --cov=<module> --cov-report=annotate:cov_annotate`）、如何读 `cov_annotate` 里的 `!` 标记行，以及在对话中给出补测用例代码。
- 覆盖提升要在用户环境执行后才能确认；本技能不得声称“覆盖率已达标”。
- 与 `jeffallan-claude-skills__test-master`（测试策略与用例设计）和 `github-awesome-copilot__test-gap-audit`（缺口审计）区分：本技能只处理 **pytest 行覆盖率的补齐循环**。
