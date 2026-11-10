# 本地使用说明（openai-skills__speech）

- 真正合成语音需要 **`OPENAI_API_KEY` + 网络**（调用 OpenAI Audio API）；本环境**未配置 key、不联网、不上传文本**。
- `allowed_tools` 仅 `read_file`：不运行 `scripts/text_to_speech.py`（也未做 `--dry-run`）、不安装 `openai` 包、不写 `output/speech/`。
- 可用部分：**脚本与指令设计**——voice 选择建议、instructions 模板、场景范例（旁白/配音/无障碍/IVR）、切分与限速规则、AI 语音披露要求。
- 生成出的音频缺失时如实说明；需要实际音频请用户在本地设置 key 后运行 CLI。
- 与已装 `video-recap-skills__video-voiceover` 的区别：后者面向视频剪辑配音编排，本技能面向 OpenAI TTS API 的语音生成规范。
