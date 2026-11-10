# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：LLM 微调方案（数据集准备、LoRA/QLoRA 选型、超参、评估、部署量化）指导。纯指导性技能，只授予 `read_file`。
- 外部依赖：实际训练需要 GPU、torch/transformers/peft/trl 等依赖，以及 Hugging Face / OpenAI 账号与模型访问权限；本地均无，也未授予 `run_bash`，未执行任何训练或评估。
- 未验证：未运行 `validate_dataset.py`（该脚本不在包内）或任何训练流程。
