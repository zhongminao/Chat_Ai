# 本地使用说明（anthropics-skills__claude-api）

## 运行限制
- 需 **Anthropic API key**（`ANTHROPIC_API_KEY`）才能真正调用 Claude；
  本环境**未配置任何 key**，且**不联网**。因此本技能只作为**离线参考手册**使用：
  查阅模型 ID、参数、SDK 写法、错误码、缓存与成本策略，再据此写代码或回答问题。
- `allowed_tools` 仅 `read_file`：不执行任何示例代码、不发起网络请求、不上传数据、
  不读写用户项目文件。

## 内容组织
- 入口 `SKILL.md` → 先判断语言，再读对应目录：
  `python/`、`typescript/`、`go/`、`java/`、`csharp/`、`php/`、`ruby/`、`curl/`。
- 跨语言通用内容在 `shared/`（模型与定价、缓存、成本、错误码、Managed Agents、
  模型迁移、提示审计等）。
- `shared/live-sources.md` 列有官方仓库/文档地址：本环境**不访问**它们，
  只用本目录内已有文件作为权威来源。

## 已知风险/注意
- 上游要求"遇到未文档化的 SDK 用法先 WebFetch 官方仓库"；本环境无网络，
  只能依据包内 `{lang}/` 文件，遇到缺失时如实告知用户，而不是凭记忆补写。
- 子命令 `migrate` / `prompt-audit` / `cost-optimize` 会修改或测量用户代码与真实
  调用（产生费用）：本环境**不执行**，只输出方案供用户自行操作。
- 不处理 OpenAI/GPT/Gemini 等其他厂商（见 excludes）。
