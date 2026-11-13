# 本地使用说明（openai-skills__playwright）

- 需要 **Node/npx 与 @playwright/cli**、浏览器运行时和网络；本环境**未安装、无网络、不执行命令**。
- `scripts/playwright_cli.sh`（`npx` 包装器）**未运行**；`allowed_tools` 仅 `read_file`，不授予 bash。
- 可用部分：**操作规范与命令参考**——open/snapshot/click/fill 的循环、何时必须重新快照、ref 失效处理、trace 与截图/PDF 产出、`references/cli.md` 命令表。
- 真实执行请用户在自己的机器上运行 `playwright-cli`；本技能只给命令序列与排查建议，不访问任何网站、不上传页面数据。
