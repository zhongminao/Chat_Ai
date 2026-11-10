# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`assets/theme.ts`、`UPSTREAM_LICENSE`（MIT, haidrrrry）为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：Remotion（React 逐帧渲染）动效视频的制作规范与可复用组件模式（弹簧缓动、错峰入场、五层画面叠加、Ken Burns、文字逐词显现、计数器、转场），以及成片抽帧自检清单。
- **运行时未安装**：需 `npm install remotion @remotion/cli react react-dom`、Node/npm，以及 Chromium/headless_shell 二进制；`npx remotion render` / `npx remotion still` / `ffmpeg` / `ffprobe` 均未在本机执行。本技能仅获 `read_file`。
- **Remotion 许可需另查**：上游仓库整体为 MIT，但 Remotion 框架本身采用另行的分级许可（公司规模阈值与商业使用条款），本项目未核实合规性；另有 `@remotion/transitions`、`@remotion/motion-blur`、`@remotion/google-fonts` 等包与 Google 字体、用户素材的许可需单独确认。上游提到的"仓库 `examples/scripts/` 音效合成脚本"未随包收录，不可用。
- 素材许可需另查：用户提供的 mp4/图片/字体/音乐不得未经授权商用；本包不含任何素材文件。
- 与已装 `video-recap-skills__*`（解说/配音/剪辑/合成）分工不同：本技能偏重"动效设计与 Remotion 代码"，不负责脚本撰写与 TTS。
- 未验证：未渲染任何视频，规则与代码片段未在真实 Remotion 项目中测试。
