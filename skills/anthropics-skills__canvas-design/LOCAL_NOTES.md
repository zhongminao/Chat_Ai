# 本地接入说明（未修改上游文件）

- `SKILL.md`、`canvas-fonts/`（54 个 .ttf + 各字体 OFL 许可文本）、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：先写"视觉哲学"，再输出静态视觉作品（.pdf / .png，90% 视觉 10% 文字），典型用途为海报、封面、宣传图。
- 字体许可：`canvas-fonts/` 内每套字体旁附 `*-OFL.txt`（SIL Open Font License），可随作品分发时需保留许可文本；未逐一复核每套字体文件与 OFL 的对应关系。
- 依赖：无脚本、无外部 API；实际产出 PDF/PNG 需绘图/排版工具（如 Python 绘图库、ImageMagick、浏览器渲染），本机是否具备未验证，本技能也无 `bash`。
- 文件写入位置由调用方决定；本技能仅获 `read_file`。
- 未验证：未产出过任何海报或画布作品。
