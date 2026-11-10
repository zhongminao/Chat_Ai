# 本地接入说明（未修改上游文件）

- `SKILL.md`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：Anthropic 官方品牌规范参考——主色/背景色/强调色（橙 `#d97757`、蓝 `#6a9bcc`、绿 `#788c5d`）、标题 Poppins + 正文 Lora（回退 Arial/Georgia）、非文字形状的强调色用法。
- 无脚本、无联网、无外部 API。
- 依赖：上游举例提到用 python-pptx 的 `RGBColor` 应用颜色，Poppins/Lora 需系统预装，本机是否安装未验证；本技能只给规范，不生成成品（生成 PPTX 请用 `office_pptx`）。
- 使用约束：这是 Anthropic 自有品牌规范，不得用于冒充 Anthropic 官方出品；第三方场景需按自身品牌替换。
- 未验证：未实际套用到任何成品文件。
