# chat_ai Agent 框架项目资料

用于确认当前 chat_ai 项目的结构、安装、运行、配置、部署及测试入口。适用于项目源码所在的不同主机，不代表机器的实时配置或状态。

1. 优先通过当前实例的 `config.yaml` 路径（或 `CHAT_AI_CONFIG`）、工作目录和源码定位项目根目录；默认 `workspace` 的父目录只是常见布局，不能作为唯一依据。核对 `README.md`、`config.yaml` 和 `pyproject.toml` 的实际路径，再按需读取。`README.md` 是通用功能、运行、配置和测试说明；`config.yaml` 是当前实例的配置。不要用 workspace 内无关文档代替项目 README，也不要将系统 `python3` 误认作项目解释器。
2. 按 README 的通用启动流程，使用符合项目要求的 Python 与 SQLite，在项目根目录安装 Python 依赖，Web 需先在 `agent/web/frontend/` 安装依赖并构建，再从项目根目录运行 `python -m uvicorn agent.web.app:app`；CLI 使用 `python -m agent.cli.main`。正式端口、Python 绝对路径、systemd unit 和是否在线由部署实例决定，不直接套用 README 示例端口。项目测试入口是 `python -m unittest discover -s tests -v`，以当前 README 和项目环境为准。
3. `agent/core/` 是 Agent 运行层；`agent/agentsessionstate/` 负责状态和上下文；`agent/model/` 是模型目录与客户端；`agent/tools/` 是工具与检索；`agent/web/` 是 Web 前后端。以当前源码和 README 为准，不能仅凭说明推断实际部署状态。
4. `workspace`、`storage_dir`、模型目录和提示词路径以当前实例的 `config.yaml` 及 `CHAT_AI_CONFIG` 为准；相对路径相对于配置文件目录。查部署时先分清开发工作树、正式运行进程、KVM 等实例。
5. 对主机的 systemd unit、真实 Python 路径、服务端口、本地模型或 KVM 网络，若另外检索到 `linux_environment` 等本机 Skill，按需读取其完整说明与相关参考资料；本项目 Skill 不保存这些私有信息。只在当前实例存在时使用，不假定其他机器也有本机 Skill。

## 交付可视化或工作区文档

项目的工作区路由只读、不列目录；Markdown 作为纯文本打开，HTML/SVG 默认作为附件下载，不在应用同源执行脚本。提供文件链接时使用当前实例 workspace 的真实绝对路径，编码特殊字符；核对文件存在并且解析后的路径在当前 workspace 内。会话附件和图片有单独的展示路由，不用本地路径伪装图片链接。

交付 HTML 前检查其 `src`、`href`、CSS `url()`、脚本及视频等相对依赖。只下载 `index.html` 不能携带旁边的图片或视频。单文件需求可以制作并验证离线可打开的自包含 HTML（大媒体不宜强行转为 data URI）；多文件则在用户授权且检查可分享后，仅归档必要资源并保持相对目录结构，提供工作区中的归档文件链接；也可改为直接交付图片、视频或 PDF。不能以开放任意工作区同源 HTML 运行来代替安全的交付设计，在线交互预览需要单独规划隔离边界。

本 Skill 不运行部署或启停脚本；涉及变更、发布、重启时遵守当前任务的授权和项目文档。
