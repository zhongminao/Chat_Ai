# Conda 与测试（初版）

## 已验证

- Conda 可执行文件：`/home/zhong/miniconda3/bin/conda`；已列出 `base`、`Snake`、`chat-ai-py313`、`proto-mj`、`proto-newton`、`py313`、`sovits`、`yzx` 环境。该列表只代表查看时的状态，不能据此推断各环境的用途。
- `chat_ai_test/README.md` 的本项目安装示例使用 `chat-ai-py313`：Python 3.13.2、SQLite >= 3.51.3、`python -m pip install -e .`。这是仓库文档的配置说明，不表示在每台机器上都完成了安装。
- 本次以 `/home/zhong/miniconda3/envs/chat-ai-py313/bin/python` 成功导入 `mcp` 并执行 `tests.test_search` 和 `tests.test_mcp_enable`，合计 6 项测试通过。系统 `/usr/bin/python3` 当时缺少 `mcp`，不能据此声称项目 Conda 环境缺包。

## 在目标项目运行测试

```bash
cd /home/zhong/mydisk/tools/chat_ai_test
/home/zhong/miniconda3/envs/chat-ai-py313/bin/python -m unittest tests.test_search tests.test_mcp_enable -q
```

项目 README 的完整后端测试命令为 `python -m unittest discover -s tests -v`（确保在相同 Conda 环境运行）。这些是**已有的测试入口**而非本 skill 附带的脚本；改变依赖或环境前先核实用户要求。
