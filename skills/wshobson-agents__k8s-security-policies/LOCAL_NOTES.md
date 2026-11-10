## 环境说明

- 纯指导型技能（无脚本）；`assets/network-policy-template.yaml` 为模板，不会被自动应用。
- 策略会改变集群网络与权限，请在测试命名空间先验证再上生产；平台不连接任何集群。
- 权限：仅 `read_file`。
