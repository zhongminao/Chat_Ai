# 本机与项目路径（初版）

## 本次观察

- 本次在该运行环境执行 `hostname` 得到 `zhong`，`uname -s -m` 得到 `Linux x86_64`；这仅说明**本次执行的主机**，不是其他服务器的清单。
- 项目工作树：`/home/zhong/mydisk/tools/chat_ai_test`；当前会话执行工具的默认工作目录是 `/home/zhong/mydisk/tools/chat_ai/workspace`，因此在 `chat_ai_test` 操作或跑测试时需显式 `cd` 到目标项目。
- 另有 `/home/zhong/mydisk/tools/chat_ai`；两套项目目录不要混淆。`chat_ai_test/skills/` 是测试项目自己的 skill 目录，`search_resources` 在其项目 workspace 运行时检索这个目录。

## 未收录

未确认生产服务器、远端 SSH 机器、容器、外网 IP、系统发行版及部署拓扑；使用前按需核实，不能将本地观察推广到其他 Linux 主机。
