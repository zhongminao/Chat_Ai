# 本地使用说明（openai-skills__aspnet-core）

- 纯本地指导型：内容全部在 `SKILL.md` 与 `references/` 15 份 Markdown 里，**不依赖任何外部账号、API key 或网络**。
- 上游建议"提到 latest 时先查 Microsoft Learn"：本环境**不联网**，因此不得声称已核对最新文档；只说内容基于包内参考文件（编于 2026-03 前后，默认 .NET 10）。
- `allowed_tools` 仅 `read_file`：不运行 `dotnet`、不生成工程、不写盘。需要实际创建/编译项目时由用户自行执行或另行授权。
- `assets/dotnet-logo.png` 仅为说明图，无脚本。
- 与已装 `jeffallan-claude-skills__dotnet-core-expert`、`csharp-developer` 的区别：本技能是 ASP.NET Core **Web 框架官方风格**参考（应用模型/管线/安全/升级），后者偏通用 C#/.NET 开发专家视角。
