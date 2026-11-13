# 本地集成说明 / LOCAL_NOTES

- 上游：zenstory-ai/video-recap-skills，commit `521214fd49bc91cb529f36abc7eaa1d6a2321aa7`；原始 `SKILL.md`、`scripts/`、`references/` 和 `UPSTREAM_LICENSE` 原样复制，`UPSTREAM_CATALOG.json` 为同批 `catalog.json` 的原样副本，MIT 版权与归属应保留。暂存包未删除。`manifest.yaml` 是本地检索元数据，不表示脚本已经验证或授权执行。
- 安全默认：`allowed_tools: [read_file]`，仅用于查看手册、输入规范与方案；**不能把检索命中理解为允许运行上游代码**。任何 `python3 scripts/...`、ffmpeg、外部 HTTP 请求都需独立评估运行环境、读写范围、输入归属、隐私与用户明确授权。不要自动将媒体、音频、帧图、旁白或转写文本发送到外部 API；尤其不能为了“预览/测试”隐式上传。所需工具与权限应另行取得，当前安装不自动授予 `bash`、网络或媒体上传权限。
- 输入输出：上游脚本会读取用户指定的媒体或 `work_dir` 中 JSON/WAV，改写/生成 `work_dir` 的中间产物与交付目录中的 MP4、字幕、QC 等；部分命令可覆盖既有输出，且可能计费或发送私人内容。权限须限定到用户同意的源和独立工作/交付目录；不得在临时检查中执行任一上游程序。
- 科学事实的来源审查、术语核验、引用与人工最终审校**不在这批技能的校验范围内**；即使 lint/QC 通过，也不能据此宣称科普结论准确。剪辑/录音/图像与声音克隆还应确认素材使用权及说话人同意。
- **不可直接跑端到端 `scripts/recap.py`**：编排器按同级 `video-understanding`、`video-script`、`video-cut`、`video-voiceover`、`video-assemble` 路径调度；本批只复制 4 个包，未提供 video-understanding / video-cut 的正式安装或完整项目根 `tools/measure_subtitle.py`，不能把残缺安装当作自足工具。还需 ffmpeg/ffprobe、MiMo 账号与密钥，按需 Fish Audio / IndexTTS；`--doctor` 只是离线配置自检不代表全链可运行。
- 默认链路会上传视频派生帧/音轨至 MiMo ASR/VLM，调用 MiMo/Fish TTS（及可选 MiMo 文本审稿）；dub 会送音频与克隆参考音色。**不要自动发送媒体给外部 API**，不要执行编排器；仅在明确获得账号、媒体外发、费用、权利与克隆同意等许可、并补齐依赖后，单独规划受控运行。输出可能覆盖工作目录和 `recap_<video>.mp4`，需检查 QC 和亲自播放，不保证科普科学事实准确。
