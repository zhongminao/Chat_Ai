# 本地使用边界（非上游原文）

- `SKILL.md`、`assets/`、`agents/`、`references/`、`scripts/`、`UPSTREAM_LICENSE` 与 `UPSTREAM_NOTICE` 为固定上游版本原样保留；此文件仅补充本地风险说明。
- 本地默认只阅读指南、参考和模板：不自动运行随包 Python 脚本，不自动 `pip install`、生成图像、联网下载素材或改写项目文件。使用脚本/引擎/第三方图像服务、安装依赖或向项目写文件前，先审查源码、输入/输出位置、依赖版本、版权及项目授权，征得相应授权。
- `scripts/asset_report.py` 导入 Pillow 并读取指定图像，输出到终端；`scripts/build_preview_sheet.py` 同样依赖 Pillow，按 `--out` 新建父目录并写入预览图，可能覆盖已有文件。脚本声明 Python 3.10+、Pillow >=10,<14；Pillow 13 需要 Python 3.11+。当前仅保留脚本，未运行、未安装依赖。
- 上游示例中的 `python -m pip install -r scripts/requirements.txt` 不是本地自动安装许可；示例图像路径也是示意，不代表文件存在。Apache-2.0 仅适用于已核对的仓库文本/脚本，不适用于后续生成/下载的图像、字体、音频、模型、引擎或品牌；每件制作素材需要独立追溯许可和使用范围。
