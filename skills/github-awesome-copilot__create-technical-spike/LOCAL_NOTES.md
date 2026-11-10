# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE` 为上游原文；本文件与 `manifest.yaml` 为本地新增。
- 上游模板含 Copilot/VS Code 提示变量（`${input:FolderPath|docs/spikes}`、`${input:SpikeTitle}` 等）与 `vscodeAPI` 工具：本环境不解析这些变量，生成时用用户提供或推断的普通文本替换，默认路径按 `docs/spikes/` 理解。
- 写盘：上游要求把 spike 文件写到 `docs/spikes/`。本 manifest **未授予** `write_file`，输出为可直接复制的 Markdown 文档；如需落盘由调用方确认路径后再写。
- 上游“Research Strategy”建议联网检索、跑原型、执行 `runTasks`：本地不联网、不运行命令，调研结论只能来自用户提供的材料或仓库内文件（`read_file`）。
- 未验证：只在 manifest 层面注册，未生成或保存任何 spike 文件。
