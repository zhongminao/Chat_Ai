# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。未修改、未执行上游文件。
- 上游附带两个 Python 脚本，本 manifest **未授予 `run_bash`，也不会运行它们**：
  - `scripts/validate_tour.py` — 校验 `.tour` 文件的路径/行号/pattern 等；
  - `scripts/generate_from_docs.py` — 从 README/docs 抽取 tour 骨架。
  替代做法：手工核对——首步锚定 `file`/`directory`、所有路径与行号在仓库中真实存在、`nextTour` 与已有 tour 标题一致、`uri` 以 `https://` 开头；字段名以 `references/codetour-schema.json` 为准。
- 上游脚本用 Claude 插件式绝对路径（`~/.agents/skills/code-tour/scripts/...`、`skills/code-tour/scripts/...`）调用；本环境不存在该路径，因此脚本调用行不可执行。
- 写盘：上游要求创建 `.tours/<name>.tour`。本 manifest **未授予 `write_file`**（且上游强调“只创建 .tour 文件”），tour JSON 以对话输出，由用户保存。
- 联网：上游建议抓取 GitHub 上的真实 `.tour` 示例；本地不联网，需用户自行提供参考内容。
- 未验证：只在 manifest 层面注册，未生成或校验任何 `.tour` 文件。
