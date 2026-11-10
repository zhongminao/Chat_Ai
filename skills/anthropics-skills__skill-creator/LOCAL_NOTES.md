# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`agents/`、`assets/`、`eval-viewer/`、`scripts/`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 均为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：撰写/改进 skill 的 SKILL.md、优化 description 触发效果、设计评测与基准对比、打包 `.skill`。纯指导为主。
- 脚本未运行、依赖未安装：`scripts/` 下 Python 工具（`run_eval.py`、`run_loop.py`、`generate_report.py`、`aggregate_benchmark.py`、`package_skill.py`、`quick_validate.py`、`improve_description.py`）需要 Python 环境及上游未声明的第三方包（评测需模型调用），本机未安装也未执行。
- `/tmp/skill-name/` 等示例路径为上游示例，不代表本机实际工作目录。
- 未验证：未对任何真实技能执行过评测、基准或打包流程；产出质量未知。产出文档的写入位置由调用方决定，本技能仅获 `read_file`。
