# 本地使用说明（anthropics-skills__academy-guide）

## 运行环境限制
- 本环境**不联网**，因此无法抓取上游要求的 Academy 目录
  （`https://academy.claude.com/assets/data/catalog.json`）。
- 所以本技能在本环境里**只能使用"规则"部分**：何时该推荐、何时应保持沉默、
  最多 2 条、禁止编造标题与链接、"先回答问题再补推荐"等。

## 实际可用做法
- 按 SKILL.md 的 Rule 7：没有目录可读时，**不要点名任何具体课程/教程**，
  只可指向文中列出的 5 个产品中心页与 `https://academy.claude.com/resources`
  这一通用资源库（这些是 SKILL.md 中明确写到的固定地址）。
- 不要根据记忆补写课程名或 /courses//tutorials/ 路径。
- 不产生任何网络请求、不上传数据；只读 SKILL.md 文本即可。

## 权限
- `allowed_tools` 仅 `read_file`。无 run_bash / 无 write_file / 无联网工具。
