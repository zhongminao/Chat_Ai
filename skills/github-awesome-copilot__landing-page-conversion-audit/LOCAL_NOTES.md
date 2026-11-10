# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 不联网：上游要求 fetch 渲染后的 DOM；本环境请用户粘贴页面文案/截图描述，或提供本地 HTML 文件（可 `read_file`）。拿不到数据时按上游规则把定量结论标为 estimate。
- 只授予 `read_file`：只输出审计与修改建议，不改页面代码、不访问真实流量数据。
- 与 `ui-ux-pro-max`（视觉/交互设计）与 `web-design-reviewer`（视觉一致性修复）区分：本技能聚焦**转化漏斗与文案/表单/信任要素**。
