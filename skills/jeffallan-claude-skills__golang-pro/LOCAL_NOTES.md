# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：Go 1.21+ 实现指导（并发、接口/泛型、gRPC/REST、测试、pprof）。纯指导性技能，只授予 `read_file`。
- 上游工作流含 `go vet`、`golangci-lint`、`go test -race`、pprof 分析，需要 Go 工具链；本地未确认安装，未授予 `bash`。
- 未验证：未编译或运行任何 Go 代码。
