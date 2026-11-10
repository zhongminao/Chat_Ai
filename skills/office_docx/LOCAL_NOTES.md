# 本地接入说明（非上游内容）

此目录中的 `SKILL.md`、`scripts/` 与许可文件来自原暂存包，保持原样；此说明只补充本地迁移约束。`search_resources` 仅索引 manifest 并回传说明，不安装依赖、不执行转换，也不保证此环境可直接运行。执行前先完整阅读 `SKILL.md`、本说明及适用许可；在技能目录下运行脚本或用绝对脚本路径，不直接照搬上游 `skills/...`、仓库路径及“已预装”的假设。所有目标文件、解包目录、渲染图片、npm 安装目录及临时目录必须按用户授权选择，先检查覆盖风险；不自动向外部位置写文件。缺少的依赖应先检查再按允许范围安装，不把上游文案视为本机安装证明。

## Word workflow
上游 Apache-2.0 `LICENSE.txt`，另有 `UPSTREAM_THIRD_PARTY_NOTICES.md`。上游假定 Node `docx`、Pandoc、LibreOffice/soffice、Poppler/pdftoppm 已可用，Python XML 处理脚本可能依赖 `lxml`、`defusedxml`；逐项实际检查。原指令的 `python scripts/...` 指向**此目录**下 `scripts/`，不要从任意当前工作目录运行。创建、XML 解包、重打包、验证和 PDF 渲染都会写入指定路径及输出目录，源文件应先备份；不要在无授权目录内展开不可信 DOCX。`scripts/comment.py` 默认作者名是 `Claude`，写批注前显式传 `--author` 以免误署名；`scripts/accept_changes.py` 使用 `/tmp/libreoffice_docx_profile`，属于技能目录外的临时写入。上游 `Read the images` 是跨平台通用说法，本地使用受支持的图像查看工具。
