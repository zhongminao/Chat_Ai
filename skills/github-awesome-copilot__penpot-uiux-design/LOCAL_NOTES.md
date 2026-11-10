# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/*`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- **外部依赖未安装**：`penpot/penpot-mcp` 服务与 Penpot 插件未在本机安装/运行，`mcp__penpot__*` 工具不可用；只授予 `read_file`，不执行 `git clone`/`npm install`，不连本机端口。
- 实际可用能力：设计原则、版式（375×812 移动端 / 1440×900 桌面）、间距/字号/颜色 token、组件清单、无障碍与 iOS/Android/Material 规范建议，均以文本形式给出；具体落地需用户自行按 `references/setup-troubleshooting.md` 安装 Penpot MCP。
- 与 `nextlevelbuilder-ui-ux-pro-max__ui-ux-pro-max`（本地可检索的设计预设库）区分：本技能是**Penpot 工具链内**的设计执行流程，不含本地预设数据。
