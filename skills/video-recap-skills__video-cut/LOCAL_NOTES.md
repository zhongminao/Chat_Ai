# 本地接入说明（未修改上游文件）

- 上游：zenstory-ai/video-recap-skills，commit `521214fd49bc91cb529f36abc7eaa1d6a2321aa7`。`SKILL.md`、`scripts/`、`references/`、`UPSTREAM_LICENSE`（MIT）为原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：两阶段创作流程的"剪辑"环节——校验 Agent 写的 `clip_plan.json`，把边界吸附到可靠句末/自然停顿并避开切镜闪帧，做必保证据 QC，拼接输出恒定帧率 `edited_source.mp4`；支持多源 `sources` manifest。
- **运行时未安装、未验证**：`scripts/cut.py`、`cut_cli.py`、`cut_render.py`、`shot_review.py`、`frame_grid.py` 等需 ffmpeg/ffprobe 与 Python 3，均未执行；本技能仅获 `read_file`。`SKILL.md` 中 `python3 scripts/cut.py ...` 属示例，脚本路径需按本目录绝对路径解析。
- **需外部 API**：剪辑本身不调用 MiMo，但作为 `video-recap` 全链一环，上游默认流程会经 `video-understanding` 使用 `MIMO_API_KEY`；本包独立使用时不需要 key。
- **素材许可需另查**：输入视频及其中人物肖像/声音需确认使用权；输出会写入 `work_dir` 并可覆盖既有产物，须限定到用户同意的工作目录。
- 依赖兄弟包：`cut` 读取上游分析阶段的 `sources`/`clip_plan`，需与 `video-understanding`、`video-assemble` 配合；目录为归档状态，非独立可运行。
- 未验证：未剪辑过任何素材，QC 阻断码与输出结构未实测。
