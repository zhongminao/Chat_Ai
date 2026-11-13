# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`data/`、`scripts/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制（MIT）；本文件与 `manifest.yaml` 为本地新增。
- 用途：本地可检索的 UI/UX 设计智能库——80 种风格（51 种启用）、192 个产品配色与推理配置、74 组字体搭配、120 条 UX 规范、105 个图标、17 个动效预设、25 种图表、22 个技术栈规则（`data/stacks/*.csv`）。
- **硬编码 Claude 插件路径（待人工处理）**：`SKILL.md` 中所有检索命令写成
  `python "${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py" ...`，
  该路径在本项目不存在，无法直接执行。替代方案：脚本按 `Path(__file__).parent.parent / "data"` 定位数据（见 `scripts/core.py`），因此把路径换成本目录的 `scripts/search.py` 即可正常工作，数据不依赖插件目录。需人工在文档层面改写后再考虑授予 `bash`。
- 脚本未运行、依赖未安装：`scripts/search.py`（检索/设计系统生成）、`design_system.py`、`validate_data.py`、`tests/` 均未执行；SKILL.md 声称仅需 Python 3.x 无第三方依赖，本机 Python 版本兼容性未验证。
- 写入类操作（`--persist` 输出设计系统文件）会写项目目录，本技能未获 `write_file`/`bash`，不做持久化。
- 未验证：数据内容未逐条核对；检索质量未知。
