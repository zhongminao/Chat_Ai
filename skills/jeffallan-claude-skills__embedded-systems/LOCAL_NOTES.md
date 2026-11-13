# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：单片机 / RTOS 固件编写与优化指导。纯指导性技能，只授予 `read_file`。
- 上游工作流含 `-Wall -Werror` 交叉编译、`cppcheck`、逻辑分析仪/示波器实测等步骤；本地无交叉编译工具链与硬件，未授予 `bash`，均未执行。
- 未验证：未编译固件，也未在真实硬件上测试。
