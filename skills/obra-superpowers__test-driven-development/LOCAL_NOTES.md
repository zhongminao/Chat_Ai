# 本地适配说明（obra-superpowers__test-driven-development）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/test-driven-development`，原文原字节复制；包内无脚本。
- 仅授予 `read_file`：纯方法论指导，本技能本身不执行测试；实际运行 `pytest`/`npm test` 等须由主 agent 在获得授权后自行执行。
- 与已装 `jeffallan-claude-skills__test-master` 区分：test-master 负责测试策略、覆盖率与用例设计；本技能只管「代码怎么写：测试先行、红绿重构」的纪律。若用户要的是测试方案或补覆盖率，用 test-master。
- 上游部分段落采用强制口吻（「必须」「违反即失败」）；在检索式体系中仅作为按需指导，不是全局规则。
