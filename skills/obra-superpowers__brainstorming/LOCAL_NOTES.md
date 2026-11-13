# 本地适配说明（obra-superpowers__brainstorming）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/brainstorming`，原文原字节复制。
- 仅授予 `read_file`。`scripts/server.cjs`、`start-server.sh`、`stop-server.sh`、`helper.js`、`frame-template.html` 是一个本地 HTTP 浏览器图形伴侣服务：**本环境没有运行、没有安装依赖（Node）、没有验证可用性**，因此不授予 `bash`。如需此功能，须人工审阅脚本、人工启动，并自行承担端口/浏览器权限风险。
- `visual-companion.md`、`builder-check-prompt.md` 可作为纯文档阅读参考。
- 上游文案要求「任何创造性工作前必须先调用本技能」并强制推进到 writing-plans 技能；在本 agent 体系中仅作为**按需检索**的指导：只有当用户确实要做方案讨论时使用，不要把它当成全局强制前置步骤。
- 跨技能依赖：上游引用 `superpowers:writing-plans`（本批已装为 `obra-superpowers__writing-plans`），不再依赖其它 obra 技能。
- 图片/草图渲染能力未在本环境验证。
