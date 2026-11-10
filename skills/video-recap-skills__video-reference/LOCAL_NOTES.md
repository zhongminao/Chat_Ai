# 本地接入说明（未修改上游文件）

- 上游：zenstory-ai/video-recap-skills，commit `521214fd49bc91cb529f36abc7eaa1d6a2321aa7`。`SKILL.md`、`scripts/`、`references/`、`UPSTREAM_LICENSE`（MIT）为原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：把一部**已完成成片**拆成下次制作可参考的"方法 + 测量数值"——ffmpeg `scdet` 测切点、测响度/LRA/真峰值、人工复核抽帧、标注音轨分工与叙事段落，导出不含原片人名台词的 `production_reference.json`。
- **运行时未安装、未验证**：`scripts/reference.py`、`reference_measure.py`、`reference_frames.py`、`reference_profile.py`、`reference_check.py`、`lib.py` 需 ffmpeg/ffprobe 与 Python 3，均未执行；本技能仅获 `read_file`。SKILL.md 中 `python3 scripts/reference.py ...` 属示例。
- **不调用外部 API**：上游明确本技能不调用 MiMo 或任何 LLM（与 `video-understanding` 不同），无 API key 依赖。
- **素材许可需另查**：需确认对被拆解成片的使用权；导出物虽剥离人名台词，仍可能含可识别的方法/结构信息，外传前自行审核。
- 依赖兄弟包：可读取上游 `video-understanding` 产物（`asr_result.json` 等），没有也能跑但旁白语速为空；目录为归档状态，非独立项目。
- 未验证：未拆解过任何成片，测量数值与泄漏扫描结果未实测。
