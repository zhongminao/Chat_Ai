# 本地适配说明（obra-superpowers__verification-before-completion）

- 上游：obra/superpowers（MIT，见 `UPSTREAM_LICENSE`），路径 `skills/verification-before-completion`，原文原字节复制；包内无脚本。
- 仅授予 `read_file`：本技能要求「亲自跑完整验证命令」，但本技能自身不执行命令；实际执行须由主 agent 使用其已获授权的工具完成。
- 上游禁止「先表达满意再验证」以及无证据的完成声明，可直接沿用；涉及 git 提交/推送的段落需要人工确认。
