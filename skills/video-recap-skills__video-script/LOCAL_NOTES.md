# 本地集成说明 / LOCAL_NOTES

- 上游：zenstory-ai/video-recap-skills，commit `521214fd49bc91cb529f36abc7eaa1d6a2321aa7`；原始 `SKILL.md`、`scripts/`、`references/` 和 `UPSTREAM_LICENSE` 原样复制，`UPSTREAM_CATALOG.json` 为同批 `catalog.json` 的原样副本，MIT 版权与归属应保留。暂存包未删除。`manifest.yaml` 是本地检索元数据，不表示脚本已经验证或授权执行。
- 安全默认：`allowed_tools: [read_file]`，仅用于查看手册、输入规范与方案；**不能把检索命中理解为允许运行上游代码**。任何 `python3 scripts/...`、ffmpeg、外部 HTTP 请求都需独立评估运行环境、读写范围、输入归属、隐私与用户明确授权。不要自动将媒体、音频、帧图、旁白或转写文本发送到外部 API；尤其不能为了“预览/测试”隐式上传。所需工具与权限应另行取得，当前安装不自动授予 `bash`、网络或媒体上传权限。
- 输入输出：上游脚本会读取用户指定的媒体或 `work_dir` 中 JSON/WAV，改写/生成 `work_dir` 的中间产物与交付目录中的 MP4、字幕、QC 等；部分命令可覆盖既有输出，且可能计费或发送私人内容。权限须限定到用户同意的源和独立工作/交付目录；不得在临时检查中执行任一上游程序。
- 科学事实的来源审查、术语核验、引用与人工最终审校**不在这批技能的校验范围内**；即使 lint/QC 通过，也不能据此宣称科普结论准确。剪辑/录音/图像与声音克隆还应确认素材使用权及说话人同意。
- 只能在已有 `agent_narration_brief.md`、VLM/ASR 等分析证据或已完成片素材基础上策划解说，Agent 生成 `recap_story_plan.json`、`visual_audio_board.json`、`narration.json`；`scripts/validate.py`/lint 设计为本地校验，但未在本次安装中执行，且机械审查不是事实审校。`scripts/review.py` 会把旁白全文与理解证据、对白转写和计划摘录发往 MiMo chat；不要自动运行，即使上游 recap 默认在 TTS 前调用。用户拒绝外发时跳过评审，仅可在另行授权后考虑离线校验。
- 与 video-understanding、video-cut、video-assemble 的 JSON/时间线合同相关，分析产物或子技能未备齐不能直接跑完整生产链。`references/research-guide.md` 的背景调研需独立核验，不能假装视频事实。
