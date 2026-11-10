# 本地接入说明（未修改上游文件）

- `SKILL.md`、`references/`、`UPSTREAM_LICENSE` 为上游原始文件逐字节复制；`manifest.yaml` 与本文件为本地新增。上游作者为 awais786（MIT）。
- 用途：Django 项目把 static/media 放到 AWS S3 的配置指导。纯指导性技能，只授予 `read_file`。
- 外部依赖：真正生效需要 AWS 账号、S3 桶、凭据/IAM 角色、`django-storages[s3]`+`boto3`；本地均无，`collectstatic`/上传等步骤未执行，也未授予 `run_bash`。
- 未验证：未连接任何 S3 或云服务；配置片段需在使用方环境自行验证。
