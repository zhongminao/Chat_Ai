# 本地使用说明（openai-skills__cloudflare-deploy）

- 需要 **Cloudflare 账号与 API Token**，并通过 `npx wrangler` 部署；本环境**未配置账号、无网络、不执行命令**。
- 可用部分：**平台选型与配置参考**（`references/` 下 60 组产品文档：workers、pages、d1、r2、kv、queues、workers-ai、ai-gateway、waf、tunnel、wrangler、terraform、pulumi 等），可离线阅读并据此给出方案、wrangler.toml 草案与排查步骤。
- `allowed_tools` 仅 `read_file`：不运行 `wrangler deploy/login/whoami`、`npm run deploy`、terraform/pulumi，不写盘、不上传、不改 DNS。
- 上游的"提权重试网络"建议在本环境**不适用**。真正部署由用户本机完成。
