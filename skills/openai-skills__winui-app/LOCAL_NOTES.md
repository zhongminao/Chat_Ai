# 本地使用说明（openai-skills__winui-app）

- 上游要求执行 `winget configure -f config.yaml`（**装 Visual Studio 与工作负载、开启开发者模式**）、`dotnet new winui`、`dotnet build`、启动应用；这些是**高风险的机器级变更**。本环境 `allowed_tools` 仅 `read_file`，**不执行任何命令、不安装软件、不改系统设置**。
- `config.yaml` 仅作为**只读参考**保留（可据此告诉用户需要哪些组件），不要运行。
- 可用部分：**设计与实现指导**——打包模式选择、XAML 结构、Shell/导航/多窗口、响应式布局、主题与 Mica、无障碍、性能与启动验证清单、参考文件 `references/`。
- 输出代码为建议，用户需在 Windows 机器上自行构建验证；本环境（非 Windows）无法验证编译结果。
