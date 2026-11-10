# 本地使用说明（openai-skills__netlify-deploy）

- 需要 **Netlify 账号与 Netlify CLI 登录**；本环境**未配置账号、无网络、不授权执行命令**。
- 用途限定为**方法论指导**：可回答部署顺序（预览优先）、netlify.toml 写法、框架发布目录、错误排查思路。
- `allowed_tools` 仅 `read_file`：不运行 `npx netlify`、`npm install`、`git remote`，不登录、不上传构建产物、不发数据。
- 上游要求"网络被沙箱阻止时申请提权重试"：本环境**不申请提权、不重试网络请求**。
- 真正部署需用户自行在本机执行，并自行确认生产部署。
