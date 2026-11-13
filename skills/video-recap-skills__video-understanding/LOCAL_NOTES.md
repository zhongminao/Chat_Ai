# 本地接入说明（未修改上游文件）

- 上游：zenstory-ai/video-recap-skills，commit `521214fd49bc91cb529f36abc7eaa1d6a2321aa7`。`SKILL.md`、`scripts/`、`references/`、`UPSTREAM_LICENSE`（MIT）为原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：视频"理解/场记"阶段——场景检测、ASR 转写、逐场景 VLM 观察、静音窗口、融合时间线，输出 `scenes.json`、`asr_result.json`、`vlm_analysis.json`、`silence_periods.json`、`timeline_fusion.json`、`agent_narration_brief.md`，供 `video-script` 等下游阶段使用。
- **运行时未安装、未验证**：需 ffmpeg/ffprobe；脚本 `scripts/understanding_runner.py`、`detect.py`、`asr.py`、`vlm.py`、`storyboard.py` 等均未执行。本技能仅获 `read_file`，无 `bash`/网络权限。
- **需外部 API（付费账号）**：ASR 使用 `mimo-v2.5-asr`、VLM 使用 `mimo-v2.5`，需 `MIMO_API_KEY`；默认 endpoint `https://api.xiaomimimo.com/v1`。**默认链路会把音频分窗与代表帧发送给 MiMo**，属媒体外发行为，须先取得账号、费用与素材外发许可，不得为测试自动上传。
- **素材许可需另查**：输入视频、其中的人物肖像/声音克隆参考需自行确认使用权与同意；导出物 `agent_narration_brief.md` 可能含对原片的描述，外传前需检查。
- 依赖兄弟包：作为两阶段流程的分析段，需与 `video-cut` / `video-script` 等同级技能配合；上游目录为归档状态、非独立可运行。
- 未验证：未分析过任何视频，产出结构正确性未知。
