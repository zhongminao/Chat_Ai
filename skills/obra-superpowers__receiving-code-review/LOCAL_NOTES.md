# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- 只授予 `read_file`：本技能**只产出处理意见**（澄清问题、逐条判定、反驳理由、修改顺序），不直接改代码（上游“one item at a time, test each”需写盘与执行测试，本环境不执行）。修改与测试由用户落地。
- 上游多处引用“your human partner 的规则”，接入后指**用户本人**。
- 与 `obra-superpowers__requesting-code-review`（发起/组织审查）、`jeffallan-claude-skills__code-reviewer`（执行审查并给合并结论）区分：本技能只处理**已收到的反馈**。
