# 本地接入说明（未修改上游文件）

- `SKILL.md`、`templates/generator_template.js`、`templates/viewer.html`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：先写"算法艺术哲学"（.md），再用 p5.js 实现带种子随机、噪声场、粒子系统的生成艺术（.html + .js），可参数交互。
- 无脚本需运行；无外部 API。**联网依赖**：生成的 viewer 通过 CDN 加载 p5.js 1.7.0 与 Google Fonts，离线环境下页面无法渲染，需自行改为本地文件（本技能未改动上游 HTML）。
- 未安装/未验证：未在浏览器中打开过生成的页面，渲染与交互效果未确认。
- 版权：上游要求创作原创算法艺术，不得复制现有艺术家作品。
