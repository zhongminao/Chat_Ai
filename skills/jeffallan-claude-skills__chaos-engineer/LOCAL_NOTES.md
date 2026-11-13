# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：混沌实验 / Game Day 设计（假设、稳态指标、爆炸半径、回滚、复盘）。纯指导性技能，只授予 `read_file`。
- 风险边界：上游示例含 `kubectl apply`、Litmus ChaosEngine 清单等真实集群操作。本接入**未授予 `bash`**，不允许据此对任何集群执行命令；示例仅供草稿参考，实际执行需人工审批（尤其生产环境）。
- 未验证：未在集群上运行过任何实验步骤。
