# 本地接入说明（非上游内容）

此目录中的 `SKILL.md`、`scripts/` 与许可文件来自原暂存包，保持原样；此说明只补充本地迁移约束。`search_resources` 仅索引 manifest 并回传说明，不安装依赖、不执行转换，也不保证此环境可直接运行。执行前先完整阅读 `SKILL.md`、本说明及适用许可；在技能目录下运行脚本或用绝对脚本路径，不直接照搬上游 `skills/...`、仓库路径及“已预装”的假设。所有目标文件、解包目录、渲染图片、npm 安装目录及临时目录必须按用户授权选择，先检查覆盖风险；不自动向外部位置写文件。缺少的依赖应先检查再按允许范围安装，不把上游文案视为本机安装证明。

## Excel workflow
上游 Apache-2.0 `LICENSE.txt`，另有 `UPSTREAM_THIRD_PARTY_NOTICES.md`。上游称 `openpyxl`、`pandas`、`markitdown`、LibreOffice 预装，这不是本地保证；根据任务逐项检测。`scripts/recalc.py` 调用 LibreOffice 且**原地重写目标工作簿**，任何宏、公式缓存、外部链接必须先核查、备份，取得保存位置授权；其临时目录及 office 用户配置也可能写入技能目录外。`python scripts/...` 必须从此目录运行或改用真实绝对路径。
