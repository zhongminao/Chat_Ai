# 本地使用说明（openai-skills__security-ownership-map）

- 需要**本地 git 仓库历史**与 Python 依赖 `networkx`；脚本内部只调用 `git log`，**不联网**（未发现 curl/requests）。
- 本环境 `allowed_tools` 仅 `read_file`：**不执行** `scripts/run_ownership_map.py` 等脚本、不安装依赖、不写 `ownership-map-out/`。
- 可用部分：**分析方案**——敏感路径规则、bus factor/孤儿代码/隐藏 owner 的定义、输出产物字段含义、`query_ownership.py` 的查询语法、Neo4j 导入 Cypher（见 `references/neo4j-import.md`）。
- 推理与结论只基于用户提供的 git 数据（如 CSV/JSON 摘录），不臆测人员或提交记录。
- 与已装 `openai-skills__security-threat-model` 的区别：后者做威胁建模，本技能做基于历史的**代码归属与维护风险**分析。
