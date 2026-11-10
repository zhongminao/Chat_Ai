# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- **Playwright MCP 未安装/未连接**，本技能不自行打开浏览器、不访问网络；只授予 `read_file`。
- 接入后的行为：按上游的探索框架（URL → 3-5 条核心流程 → 元素/定位器/预期结果 → 关闭上下文 → 总结 → 提测试用例）指导用户，并读取用户提供的页面结构（HTML、截图描述、已有 e2e 代码）来产出探索记录与测试用例草案。
- 与 `anthropics-skills__webapp-testing` 与 `github-awesome-copilot__webapp-testing`（Playwright 执行测试）区分：本技能只做**探索与用例设计**，不写执行脚本。
