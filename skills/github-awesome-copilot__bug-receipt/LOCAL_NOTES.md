# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`assets/`、`UPSTREAM_LICENSE` 为上游原文（MIT，上游 https://github.com/lMysticl/bug-receipt）；本文件与 `manifest.yaml` 为本地新增。
- `scripts/validate-receipt.mjs` 为 Node 脚本，**未运行、未验证**；不授予 `bash`。需要 JSON 回执时，按 `references/receipt-contract.md` 与 `references/receipt.schema.json` 人工核对字段。
- 只授予 `read_file`：本技能不自行执行测试或命令，`Proof` 一栏只接受用户提供或对话中已出现的证据，**不得编造命令/日志/结果**；未执行的检查一律写 `not run`。
- 与 `obra-superpowers__verification-before-completion`（完成前证据门槛）分工：后者针对“功能完成”声明，本技能针对**缺陷/事故结案**的固定回执格式和状态判定。
- 上游 `Source: executed now | supplied | mixed` 需如实标注证据来源。
