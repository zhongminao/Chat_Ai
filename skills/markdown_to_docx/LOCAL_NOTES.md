# 本地接入说明（非上游内容）

此目录中的 `SKILL.md`、`scripts/` 与许可文件来自原暂存包，保持原样；此说明只补充本地迁移约束。`search_resources` 仅索引 manifest 并回传说明，不安装依赖、不执行转换，也不保证此环境可直接运行。执行前先完整阅读 `SKILL.md`、本说明及适用许可；在技能目录下运行脚本或用绝对脚本路径，不直接照搬上游 `skills/...`、仓库路径及“已预装”的假设。所有目标文件、解包目录、渲染图片、npm 安装目录及临时目录必须按用户授权选择，先检查覆盖风险；不自动向外部位置写文件。缺少的依赖应先检查再按允许范围安装，不把上游文案视为本机安装证明。

## Markdown → Word
上游 MIT `UPSTREAM_LICENSE`。需要 Node.js 18+、`docx` 9+ 与 `marked` 15+，但 `scripts/package.json` 声明的是 `docx:^9.6.1`、`marked:^17.0.4`；版本与环境兼容性先实测，不能声称直接可运行。上游 `cd skills/md-to-docx/scripts` 是旧仓库**相对目录**，这里实际为本技能目录 `scripts/`，应在受控允许的环境中安装（npm install 会写入 `scripts/node_modules` 和可能的锁文件/缓存，甚至访问网络；安装前需获得相应权限）。转换脚本写出 `.docx`，省略输出路径则在**当前工作目录**写 `<input-basename>.docx`，可能覆盖现有文件；始终使用用户授权的显式输出路径。上游所谓 no external tools 仅指无 Pandoc/LibreOffice，不代表不需要 Node/npm 依赖。
