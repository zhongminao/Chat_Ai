# 本地使用说明（openai-skills__pdf）

## 三个 PDF 技能的分工
- `pdf_reader`：读取已有 PDF 正文，带固定脚本、OCR 兜底。查询"读取/总结 PDF 文字"走它。
- `anthropics-skills__pdf`：制作与修改——合并、拆分、旋转、水印、加密、表单填写。
- 本技能（`openai-skills__pdf`）：**重视排版的生成与视觉校验**——reportlab 生成、`pdftoppm` 渲染成图后目视检查、pdfplumber/pypdf 抽取。本技能不抢占读取/合并/表单类查询（见 manifest 的 excludes）。

## 运行限制
- `allowed_tools` 仅 `read_file`：不执行命令、不写盘、不安装依赖。
- 依赖（reportlab、pdfplumber、pypdf、poppler/pdftoppm）**未安装、未验证**。真正执行需由用户授权后在本机安装。
- 上游约定写到 `tmp/pdfs/` 与 `output/pdf/`；本仓库未开放写权限，只输出代码与步骤。
- 无环境变量要求；不联网、不上传 PDF 内容。

## 许可
上游 Apache-2.0，原文见 `LICENSE.txt`；`agents/openai.yaml` 为上游 Codex 界面元数据，未在本项目启用。
