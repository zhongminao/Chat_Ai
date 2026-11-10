## 环境说明

- 纯指导型技能（无脚本）；示例中的 `pip install semgrep`、`docker run sonarqube`、`codeql database create` 等命令平台不会执行，也不会安装任何工具或拉起容器。
- Semgrep/SonarQube/CodeQL 均为外部工具，部分功能（SonarQube 商业版、GitHub Advanced Security）需要账号或付费许可。
- 生成的扫描配置请先人工审阅，再在用户自己的仓库/CI 中应用。
- 权限：仅 `read_file`。
