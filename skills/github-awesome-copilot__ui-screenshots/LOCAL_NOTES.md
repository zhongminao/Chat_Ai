# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- **未安装 Playwright / Pillow / Chromium**，本技能不自行启动浏览器或截图；只授予 `read_file`。
- 接入后的行为：给出可复制的 Playwright 截图脚本、PIL 裁切与 `mss`/`ctypes` 桌面截图的方案说明和注意事项（高视口、networkidle、等待动画、迭代裁切而不是重复截图），由用户在本机执行。
- 与 `anthropics-skills__webapp-testing` / `github-awesome-copilot__webapp-testing`（功能验证）与 `web-design-reviewer`（设计问题修复）区分：本技能只负责**截图留档流程**。
