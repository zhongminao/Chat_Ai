# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。
- 用途：Django / DRF 实现指导（模型、迁移、序列化器、视图、鉴权、测试）。纯指导性技能，只授予 `read_file`。
- 上游工作流含 `manage.py makemigrations/migrate`、`curl` 验证等步骤，需要可运行的 Python/Django 环境；本地未安装、未授予 `bash`。
- 未验证：未运行任何 Django 项目或测试。
