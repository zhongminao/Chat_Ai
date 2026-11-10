# 本地接入说明（未修改上游文件）

- `SKILL.md`、`UPSTREAM_LICENSE`（MIT, Promptible）为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：Remotion 连续场景运镜规范——一个大于视口的共享世界，单条 focal/zoom 关键帧时间轴，HIT→hold→travel→settle 编排，反霓虹/发光/毛玻璃的视觉禁令，以及首轮验收与抽帧 QA 清单。
- **依赖未满足（不可独立运行）**：SKILL.md 明确要求配合 `remotion-best-practices` 与 `motion-graphics` 两个技能包一起使用，本机均未安装；"强制已批准参考复核"环节还要求访问该项目以往已批准的成片与源码（含 GitHub 画廊 `https://github.com/Liamrjohnston/remotion-motion-graphics-skill`），本机无这些素材且未联网。
- **运行时未安装**：Remotion / Node / 浏览器渲染器 / ffmpeg 均未安装，未执行任何渲染或抽帧；本技能仅获 `read_file`。
- **许可需另查**：仓库为 MIT，但 Remotion 框架采用另行分级许可；用户素材（logo、截图、footage）许可需单独确认，本包不含素材文件。
- 未验证：未产出任何镜头动画，运镜参数与 QA 结论均未实测。
