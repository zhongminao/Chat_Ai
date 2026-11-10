# 本地接入说明（未修改上游文件）

- `SKILL.md`、`themes/`、`theme-showcase.pdf`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：提供 10 套预设主题（配色 + 字体搭配，见 `themes/*.md`）及 `theme-showcase.pdf` 预览，用于给幻灯片、报告、HTML 页面统一风格，或自拟主题。
- 无脚本、无联网、无外部 API；仅需读取 `themes/` 与 `theme-showcase.pdf`。
- 注意：本技能只产出主题规范，不生成 PPTX/PDF 等成品；成品生成请用 `office_pptx` 等已有技能。字体需本机具备对应字体才可真实渲染。
- 未验证：未实际套用到任何成品文件中。
