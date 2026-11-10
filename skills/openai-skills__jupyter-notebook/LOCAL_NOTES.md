# 本地适配说明（openai-skills__jupyter-notebook）

- 上游：openai/skills（Apache-2.0，见 `LICENSE.txt`），`.curated/jupyter-notebook`，原文原字节复制。
- 仅授予 `read_file`。包内 `scripts/new_notebook.py`（仅用标准库，加载模板并改写标题后写出 .ipynb）**未运行、未验证**；本技能也 **未授予 `run_bash` 与 `write_file`**，因此不能在本环境直接生成 .ipynb 文件。
- 可用做法：阅读 `assets/*.ipynb` 模板与 `references/notebook-structure.md`，由主 agent 在用户要求下手工写 notebook JSON（需要写文件能力时另行授权）。
- 上游把脚本路径写死为 `$CODEX_HOME/skills/jupyter-notebook/scripts/new_notebook.py`，本地实际路径是 `chat_ai_test/skills/openai-skills__jupyter-notebook/scripts/new_notebook.py`；上游 `uv run --python 3.12` 与 `uv pip install jupyterlab ipykernel` 依赖均**未安装**。
- 上游输出约定 `output/jupyter-notebook/`、`tmp/jupyter-notebook/` 只适用于代码仓库工作；在 chat_ai_test 中不要擅自写这些目录。
- 执行 notebook（top-to-bottom）需要 Jupyter 内核，本环境不具备，无法验证可运行性。
