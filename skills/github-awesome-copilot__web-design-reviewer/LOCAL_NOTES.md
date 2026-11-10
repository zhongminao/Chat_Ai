# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/visual-checklist.md`、`references/framework-fixes.md`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- 只授予 `read_file`：**不截图、不启动浏览器、不改代码**。上游依赖「浏览器自动化 + 源码修复循环」，本环境无 Playwright/MCP、无 run_bash/write_file，因此：
  - 视觉证据需由用户提供（截图、DOM 片段或粘贴的 HTML/CSS）；
  - 结论只基于用户给出的材料，**不得凭想象描述页面长相**；无法判断的项标为“需截图确认”。
- 输出为**问题清单 + 建议修改**（选择器/CSS 属性/断点），由用户落地；参考 `references/framework-fixes.md` 中的框架级修法。
- 区分：`wshobson-agents__design-system-patterns`（令牌与组件库架构，建设期）、`anthropics-skills__frontend-design`（新页面视觉方向与创意）、`nextlevelbuilder-ui-ux-pro-max__ui-ux-pro-max`（风格/配色/字体/UX 规则查询）、`github-awesome-copilot__landing-page-conversion-audit`（转化率角度审计）。本技能只做**已运行页面的视觉缺陷巡检**。
