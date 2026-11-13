# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：REST/GraphQL 接口设计与 OpenAPI 3.1 规格撰写。纯指导性技能，只授予 `read_file`。
- 上游工作流提到的 `npx @redocly/cli lint`、`npx @stoplight/prism-cli mock` 依赖 Node 及网络拉取包，本地未安装、未运行，也未授予 `bash`；相关校验步骤需由调用方自行决定是否执行。
- 未验证：未对任何真实 API 运行过该流程。
