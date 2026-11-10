# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE`（MIT）为上游原文；`manifest.yaml` 与本文件为本地新增。
- 只授予 `read_file`：**不写盘**，生成的索引表以 markdown 片段形式在回复中给出，由用户粘贴到目标文件。
- 上游使用 VS Code Copilot 变量 `${file}` / `${input:folder}` / `${input:pattern}`，本环境**不解析**；需用户在请求里给出目标 markdown 文件、目录路径与可选的文件匹配模式。
- 文件清单来自用户提供的目录内容（文件树/`ls` 输出）或 `read_file` 读到的既有清单；本技能不列目录，缺目录信息时先向用户索取。
- 与 `create-readme`（从零写完整 README）、`create-llms`/`update-llms`（llms.txt）区分：本技能只产出**某目录的文件索引表/清单**。
