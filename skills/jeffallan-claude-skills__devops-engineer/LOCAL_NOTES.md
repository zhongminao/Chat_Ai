# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：CI/CD 流水线、Dockerfile、K8s 清单、Terraform、发布与故障响应指导。纯指导性技能，只授予 `read_file`。
- 风险边界：上游工作流含 `terraform plan/apply`、`kubectl`、部署与生产发布步骤。本地无这些工具与凭据，也**未授予 `run_bash`**；任何 apply/部署/回滚命令均不得由本技能执行，需人工审批。
- 未验证：未执行任何流水线或基础设施命令。
