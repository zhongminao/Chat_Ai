# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：PostgreSQL/MySQL 慢查询与执行计划分析、索引与参数调优建议。纯指导性技能，只授予 `read_file`。
- 边界：`EXPLAIN ANALYZE`、改索引、改配置等需直连数据库；本地无数据库连接、未授予 `bash`。建议一律在非生产验证。
- 未验证：未连接任何数据库，优化结论需人工复核。
