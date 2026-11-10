# 本地接入说明（未修改上游文件）

- `SKILL.md`、`scripts/coverage_map.py`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 只授予 `read_file`：审计**只读**，不执行测试、不改测试代码；`scripts/coverage_map.py` **未运行、未验证**（用户可在终端自行 `python <skill-dir>/scripts/coverage_map.py --top 25`）。
- 若未运行脚本，改为手动对照源文件与测试目录/命名约定，并按上游要求把“未匹配”当线索、确认后才报 P0/P1。
- 与 `pytest-coverage`（行覆盖率补齐循环）、`breakdown-test`（从需求做测试计划）、`test-master`（写测试）区分。
