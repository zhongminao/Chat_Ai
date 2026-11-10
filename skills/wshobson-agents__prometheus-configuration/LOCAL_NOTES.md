## 环境说明

- 纯指导型技能（无脚本）；示例里的 `curl http://localhost:9090/api/v1/targets` 等命令需要用户自己已有 Prometheus 实例才能执行，平台不会连接任何监控服务。
- 生成的 `prometheus.yml`、告警规则 YAML 应由用户在目标环境审核后应用。
- 权限：仅 `read_file`。
