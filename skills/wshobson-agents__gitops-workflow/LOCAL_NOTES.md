## 环境说明

- 纯指导型技能（无脚本）；示例中的 `kubectl apply -f https://raw.githubusercontent.com/...`、`brew install fluxcd/tap/flux` 等命令平台不会执行，也不会联网拉取清单。
- ArgoCD/Flux 需要用户自己的 Kubernetes 集群与 Git 仓库访问权限；自动同步（prune/selfHeal）影响生产集群，请先在测试集群验证。
- 请勿把明文凭据写入 Git 仓库，使用 SOPS/Sealed Secrets/外部密钥管理。
- 权限：仅 `read_file`。
