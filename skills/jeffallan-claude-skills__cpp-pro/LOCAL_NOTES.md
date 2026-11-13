# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：现代 C++（C++20/23）编写、重构、性能与并发问题排查指导。纯指导性技能，只授予 `read_file`。
- 上游工作流包含 CMake 构建、AddressSanitizer/UBSan、静态分析、基准测试等步骤；本地未确认有 C++ 工具链，且未授予 `bash`，这些校验步骤需调用方自行判断。
- 未验证：未编译或运行任何 C++ 代码。
