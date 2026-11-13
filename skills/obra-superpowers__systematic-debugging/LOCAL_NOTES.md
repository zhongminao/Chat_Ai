# 本地适配说明（obra-superpowers__systematic-debugging）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/systematic-debugging`，原文原字节复制。
- 仅授予 `read_file`：本技能是排查方法论。包内 `find-polluter.sh`（查找污染测试的脚本）**未运行、未验证**，不授予 `bash`；`condition-based-waiting-example.ts` 只是 TypeScript 示例。
- 与已装 `jeffallan-claude-skills__debugging-wizard` 区分：debugging-wizard 覆盖通用排错、堆栈/日志分析与回归测试约定；本技能强调「禁止在根因调查完成前改代码」的四阶段纪律与跨组件诊断埋点、条件等待、纵深防御等具体技术。二者命中同一查询时允许并存，优先按用户意图选择。
- 上游要求的「写回归测试前先复现」需实际执行测试命令，须由主 agent 在获得授权后执行。
