# 本地接入说明（未修改上游文件）

- `SKILL.md`、`scripts/with_server.py`、`LICENSE.txt`、`UPSTREAM_THIRD_PARTY_NOTICES.md` 为上游原始文件逐字节复制；本文件与 `manifest.yaml` 为本地新增。
- 用途：用 Python Playwright 测试本地 Web 应用（功能验证、UI 调试、截图、浏览器日志）；`scripts/with_server.py` 负责启停 dev server。
- 脚本未运行、依赖未安装：需 `playwright` Python 包及 `playwright install` 浏览器（未安装），被测试应用还需其自身 Node/Python 运行时。本机未执行 `with_server.py`。
- 上游说明要求"先运行脚本 `--help`、不要先读源码"，本技能无 `bash`，只能阅读脚本与说明作为参考。
- 仅适用于本机可访问的 localhost 应用；不要对公网目标使用。
- 未验证：未针对任何应用执行测试，脚本行为与兼容性未确认。
