# 本地使用说明（openai-skills__transcribe）

- 真正转写需要 **`OPENAI_API_KEY` + 网络**，并把音频**上传**给 OpenAI API；本环境**未配置 key、不联网、不上传任何音频**。
- `allowed_tools` 仅 `read_file`：不运行 `scripts/transcribe_diarize.py`、不安装 `openai` 包、不写 `output/transcribe/`。
- 可用部分：**方法论与限制**——`gpt-4o-mini-transcribe`（快速文本）与 `gpt-4o-transcribe-diarize`（分离）的取舍、mp3/m4a/wav/webm 等格式与 25MB 上限、30 秒以上分块、最多 4 个已知说话人、`diarized_json` 不支持 prompting、输出校验要点。
- 用户实际转写时请自行配置 key 并运行 CLI；可把转写文本贴回来继续分析。
