# Linux 环境与部署说明（初版）

用于回答本机 Linux / `chat_ai_test` 的环境、Conda、运行与本地服务配置问题。本 skill 是可检索的说明入口，不执行部署，不保证机器状态长期不变。只有已核实的信息才写成事实；变动前核对当前配置和实际运行状态。

## 按需读取模块

- `references/host_and_paths.md`：已见到的本机平台、工作目录与项目边界。
- `references/conda_and_tests.md`：Conda 环境选择、测试命令、系统 Python 的常见误用。
- `references/services_and_deployment.md`：`chat_ai_test` 的配置文件、Web 开发/启动方式、MCP 地址与状态区分。

`search_resources` 结果含以上引用文件的**绝对路径**；使用 `read_file` 读取所需模块。若搜索结果未提供该路径，先查看 `manifest.yaml` 的 `references`，不要猜测脚本路径。没有固定脚本；需验证状态时可用现有 `run_bash` 只读命令，代码更改/启动/部署按用户当前授权范围进行。

## 使用约束与扩展

1. 区分“仓库文档/配置声明”和“当前机器/进程实测”；`127.0.0.1` 地址写在配置里不代表服务在线。MCP 连接遵守 `enable_mcp` 的用户明确授权要求；不要因本 skill 命中就连接。
2. 优先显式指定 `/home/zhong/miniconda3/envs/chat-ai-py313/bin/python` 跑本项目测试；不要把 `/usr/bin/python3` 缺包误判为项目环境缺包。运行前核对项目路径、配置文件与环境。
3. 不在 skill 中写密码、Token、私钥。不要凭空推断公网 IP、SSH 主机、代理、生产部署、个人编码偏好等未记录事实。
4. 新增主题时在 `references/` 下增设单独文件，并更新本索引与 `manifest.yaml` 的 `references`；当有**已确认**的代码习惯或正式部署步骤时再补相应模块。此 skill 不代替项目 README 或现行配置。
