# 本地使用说明（openai-skills__gh-fix-ci）

- 需要 **GitHub CLI `gh` 已登录**（repo + workflow scope）；本环境**未认证、无网络、不执行命令**。
- `scripts/inspect_pr_checks.py` **未运行、未安装依赖**；`allowed_tools` 仅 `read_file`，不授予 run_bash/write_file。
- 可用部分：**方法论**——失败检查定位顺序、日志摘要该写什么、外部 CI 只报 URL、先计划后改动的审批门槛。
- 用户实际排查时请自行运行 `python scripts/inspect_pr_checks.py --repo . --pr <n>` 或 `gh pr checks`，把输出贴回来再分析。
- 不申请提权、不登录、不修改仓库。
