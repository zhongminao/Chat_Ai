# 本地使用说明（anthropics-skills__pdf）

## 与已装 `pdf_reader` 的分工（重要）
- `pdf_reader`（自带 run_bash + 固定脚本）：**读取/总结已有 PDF 正文、布局、OCR 兜底**。
  查询如"读取 PDF""提取 PDF 文字""总结 PDF""扫描件 OCR"都应由 pdf_reader 优先处理，
  本技能 manifest 已把这几类写入 `excludes`，不会抢占。
- 本技能：**制作与修改 PDF**——用 pypdf / pdfplumber / reportlab / qpdf / pdftk /
  pdfimages 合并、拆分、旋转、加水印、加密解密、抽图抽表、生成新 PDF，
  以及 forms.md 描述的 **PDF 表单填写**流程（fillable 与 non-fillable 两条路径）。

## 运行限制
- 本技能只读：`allowed_tools` 仅 `read_file`。**不授予 run_bash/write_file**，因此
  SKILL.md/reference.md 中的代码与 `scripts/*.py` 不会被自动执行，也不会写盘。
- `scripts/` 下 8 个 Python 脚本（依赖 pypdf、pdfplumber、reportlab、pdf2image 等）
  **未安装依赖、未运行、未验证**。需要真正执行时，请由用户自行安装依赖并授权运行。
- 使用方式：把 SKILL.md 的代码片段与操作步骤作为参考答案输出给用户，
  或说明"需授权后在本地环境运行 scripts/xxx.py"。
- 不联网、不上传：任何 PDF 内容都不发送到托管文档服务。

## 上游许可
- 见 `LICENSE.txt` 与 `UPSTREAM_THIRD_PARTY_NOTICES.md`（未修改）。
