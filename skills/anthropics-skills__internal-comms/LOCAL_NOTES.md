# 本地接入说明（未修改上游文件）

- `SKILL.md`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：内部沟通写作指引（3P 更新、公司通讯、FAQ、状态报告、领导层更新、事故通报、项目更新）。
- **缺文件**：`SKILL.md` 指引读取 `examples/3p-updates.md`、`examples/company-newsletter.md`、`examples/faq-answers.md`、`examples/general-comms.md`，但暂存包中无 `examples/` 目录（上游仓库抓取时未收录）。因此仅能按 SKILL.md 正文的沟通类型清单给出通用结构，具体格式模板不可用；如需完整模板须回上游仓库 `anthropics/skills` 补充 `examples/`。
- 无脚本、无联网、无外部 API、无依赖。
- 未验证：未实际撰写过成稿；产出质量未知。
