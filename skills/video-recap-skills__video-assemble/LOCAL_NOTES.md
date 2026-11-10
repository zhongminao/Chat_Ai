# 本地集成说明 / LOCAL_NOTES

- 上游：zenstory-ai/video-recap-skills，commit `521214fd49bc91cb529f36abc7eaa1d6a2321aa7`；原始 `SKILL.md`、`scripts/`、`references/` 和 `UPSTREAM_LICENSE` 原样复制，`UPSTREAM_CATALOG.json` 为同批 `catalog.json` 的原样副本，MIT 版权与归属应保留。暂存包未删除。`manifest.yaml` 是本地检索元数据，不表示脚本已经验证或授权执行。
- 安全默认：`allowed_tools: [read_file]`，仅用于查看手册、输入规范与方案；**不能把检索命中理解为允许运行上游代码**。任何 `python3 scripts/...`、ffmpeg、外部 HTTP 请求都需独立评估运行环境、读写范围、输入归属、隐私与用户明确授权。不要自动将媒体、音频、帧图、旁白或转写文本发送到外部 API；尤其不能为了“预览/测试”隐式上传。所需工具与权限应另行取得，当前安装不自动授予 `run_bash`、网络或媒体上传权限。
- 输入输出：上游脚本会读取用户指定的媒体或 `work_dir` 中 JSON/WAV，改写/生成 `work_dir` 的中间产物与交付目录中的 MP4、字幕、QC 等；部分命令可覆盖既有输出，且可能计费或发送私人内容。权限须限定到用户同意的源和独立工作/交付目录；不得在临时检查中执行任一上游程序。
- 科学事实的来源审查、术语核验、引用与人工最终审校**不在这批技能的校验范围内**；即使 lint/QC 通过，也不能据此宣称科普结论准确。剪辑/录音/图像与声音克隆还应确认素材使用权及说话人同意。
- 依赖媒体/编解码环境：ffmpeg/ffprobe 和对应 libass、drawtext 扩展（缺失时字幕烧录降级或失败）；需要源媒体、经过确认的 `tts_meta.json` 与其 WAV、相关采纳合同；直接运行 `scripts/assemble.py` 会写/覆盖 `recap_<stem>.mp4`、`work_dir/output.mp4`、SRT/ASS、时间线、混音与质量报告，可能在可选 `--export-jianying` 时复制媒体到草稿目录。`references/jianying/LICENSE.duo-video` 也是上游附带第三方模板许可，保留其归属。
- 上游 assemble 预期理解/剪辑/配音等兄弟技能提供时间线和音频，单凭包本身不够生产；仅单独阅读或评估流程，不自动执行合成脚本。此阶段设计本地 ffmpeg 处理、不会自行将媒体发 API；若前序 TTS/评审或其它编排阶段启用，仍必须另行控制外发。
