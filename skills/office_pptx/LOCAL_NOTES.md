# 本地接入说明（非上游内容）

此目录中的 `SKILL.md`、`scripts/` 与许可文件来自原暂存包，保持原样；此说明只补充本地迁移约束。`search_resources` 仅索引 manifest 并回传说明，不安装依赖、不执行转换，也不保证此环境可直接运行。执行前先完整阅读 `SKILL.md`、本说明及适用许可；在技能目录下运行脚本或用绝对脚本路径，不直接照搬上游 `skills/...`、仓库路径及“已预装”的假设。所有目标文件、解包目录、渲染图片、npm 安装目录及临时目录必须按用户授权选择，先检查覆盖风险；不自动向外部位置写文件。缺少的依赖应先检查再按允许范围安装，不把上游文案视为本机安装证明。

## PowerPoint workflow
上游 Apache-2.0 `LICENSE.txt`，另有 `UPSTREAM_THIRD_PARTY_NOTICES.md`。上游称 `pptxgenjs`、`markitdown[pptx]`、`Pillow`、`defusedxml`、`lxml`、`react-icons`/`react`/`react-dom`/`sharp`、LibreOffice 及 Poppler 已安装，均应实际核查。脚本实际位置是此目录 `scripts/`；例如缩略图默认名 `thumbnails` 会覆盖同目录旧文件；`scripts/add_slide.py` 未传 `-o` 可能原地重写输入；渲染 PDF/JPEG、unpacked 目录和临时 office 配置均会写文件，应在用户允许的目的地执行并确认覆盖。上游“subagent works well”和“view tool”只是可选平台建议，本代理不能委派；可在权限内用 read_image 检查渲染图。
