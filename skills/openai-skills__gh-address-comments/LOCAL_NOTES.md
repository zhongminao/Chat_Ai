# 本地使用说明（openai-skills__gh-address-comments）

- 需要 **GitHub CLI `gh` 已登录**（repo scope）；本环境**未配置认证、无网络、不执行命令**。
- `scripts/fetch_comments.py` **未运行、未安装依赖**；`allowed_tools` 仅 `read_file`，不授予 bash/write_file。
- 可用部分：**流程指导**——如何列评审线程编号、给出每条修复代价摘要、请用户勾选后逐条修改。
- 若用户需要实际拉取 PR 评论，请用户自行运行 `python scripts/fetch_comments.py`（或提供评论内容）后再继续。
- 不申请提权、不 `gh auth login`、不写入 GitHub。
