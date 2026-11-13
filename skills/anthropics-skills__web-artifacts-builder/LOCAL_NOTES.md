# 本地接入说明（未修改上游文件）

- `SKILL.md`、`scripts/init-artifact.sh`、`scripts/bundle-artifact.sh`、`scripts/shadcn-components.tar.gz`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：搭建 React 18 + TypeScript + Vite + Tailwind + shadcn/ui 项目，并把成品打包成单文件 HTML（claude.ai artifact 形式）。
- 脚本未运行、依赖未安装：`scripts/init-artifact.sh` 会执行 npm 安装（React/Vite/Tailwind/shadcn 及 Radix 依赖），`scripts/bundle-artifact.sh` 会安装 parcel/html-inline 等打包依赖并构建；本机未执行，Node/npm 依赖均未安装。`shadcn-components.tar.gz` 仅为静态组件包，未解压。
- 定位为 "claude.ai artifact"：产物的展示/分享方式依赖 claude.ai 对话界面；在本项目内只能生成文件，无法上传到 claude.ai。
- 本技能仅获 `read_file`：不能写工程文件或运行构建命令；如走完整流程需人工或授予 `write_file`/`bash` 后再评估。
- 未验证：未执行任何构建，单文件 HTML 产物质量未知。
