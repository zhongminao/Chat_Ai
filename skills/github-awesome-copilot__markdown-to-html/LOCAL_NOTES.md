# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 依赖：上游建议 `npm install -g marked` 或本地安装 marked，也可用 pandoc；本仓库**未安装**这些依赖，也未执行转换。
- 权限：`run_bash` 仅用于调用已存在的转换命令并输出到指定路径；不得自行安装软件包、上传文档或覆盖非目标文件。
- 未验证：所有转换示例（表格、代码块、数学公式、Jekyll/Hugo）均未实际渲染验证。
