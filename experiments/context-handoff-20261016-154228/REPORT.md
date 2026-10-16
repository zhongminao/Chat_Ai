# chat_ai 上下文交接实验

模型：本地 `local-qwen3-coder-30b / qwen3-coder-30b`。任务：开发离线浏览器游戏《星港回收站》，分引擎、界面/存档/回放、冲刺与最终验证三个阶段。

## 已确认的结果

外置脚本完成了“达到阈值 → 原会话读取 skill → 模型写 JSON 计划 → 程序复制选定内容 → 新 ID 接收冻结输入”的完整流程。没有修改 chat_ai 的 AgentRuntime、SessionRegistry、状态恢复、Web API、模型配置或前端。

| 项目 | 实测 |
| --- | ---: |
| 触发阈值 | 32768 token |
| 触发时上一轮服务用量（输入＋输出） | 33760 token |
| 冻结历史的输入（包含工具说明） | 35288 token |
| 新会话输入（包含相同工具说明） | 10009 token |
| 输入减少 | 71.64% |
| 新会话首轮服务实际 prompt_tokens | 10009 |
| 完整保留的实验用户输入 | 3 条 |
| 原历史消息组 → 选中消息组 | 42 → 2 |
| 当前文件片段 | 3 份 |
| 摘要长度 | 660 字符 |
| 整理过程模型调用 / 总输出 | 5 次 / 912 token |
| 整理用时 | 149.7 秒 |

阈值在完整工具组后检查，故不会恰好停在第32768个token。冻结历史还包含工具结果，因此与上一轮服务用量不同。新会话的计数由模型服务的 `/apply-template` 和 `/tokenize` 得到，并与真实生成接口首轮用量一致。

整理时的最大单次模型输入为46481 token：除了原历史，还读入了skill、清单和一段快照。此次没有需要输出大量旧代码，但整理材料的重复读取仍有约11K token的额外输入，应在以后设计阈值时考虑。

## 网页会话与服务器文件

- 原会话：`上下文整理实验 · 游戏开发原会话`，ID `0424f73355f648cf9a8198152156750d`。
- 新会话：`上下文整理实验 · 游戏开发续接会话`，ID `946e1769d6d349e6baa5cbd1bb41c4e7`。
- 项目：`/home/zhong/mydisk/tools/chat_ai`。
- Skill：`/home/zhong/mydisk/tools/chat_ai/skills/context-handoff/SKILL.md`。
- 脚本：`/home/zhong/mydisk/tools/chat_ai/skills/context-handoff/scripts/handoff.py`。
- 实验资料：`/home/zhong/mydisk/tools/chat_ai/experiments/context-handoff-20261016-154228`。
- 游戏：`/home/zhong/mydisk/tools/chat_ai/workspace/context-handoff-game-20261016-154228`。

两个会话均通过现有HTTP接口创建，网页历史列表可见；原会话没有被删除。此次是独立实验，不是给所有生产会话启用了自动压缩。

## 精确性验证

- 原会话截至冻结点的事件字节SHA-256仍一致，没有重写旧事件。
- 3条实验用户输入在bundle中逐字、按顺序保留。
- 新会话第一条真实输入与bundle保存的输入完全一致。
- bundle保存选中文件的具体内容和完整文件指纹；之后游戏文件继续修改，不会改变已保存的输入。
- 脚本4项测试通过：工具调用/回执整组保留，冻结内容与用户原文保持一致，无效引用/范围/预算拒绝，目录越界/符号链接越界拒绝。
- Skill通过skill-creator的quick_validate检查。

## 首次续接的限制

不能据此宣称“压缩后无损完成任务”。首次续接进入开发流程，但7次edit_file中有6次old与new完全相同；为避免无效重复，实验主动停止了该轮，终止事件为turn.cancelled。未经额外反馈的首次续接代码、事件和测试分别保存在game-first-continuation、first-continuation-events.jsonl、evaluation-first-continuation.txt中。

摘要存在语义错误与矛盾：声称阶段2完成，同时承认回放尚未实现；把无效移动规则说成可能允许，与明确用户要求冲突。原始用户输入没有丢失，但这并不能保证模型一定正确使用它们。

冻结时的独立引擎验证共10项，5通过、5失败：基础规则6项中5通过、1项地图检查失败；冲刺4项尚未实现。浏览器还存在`require is not defined`，游戏未初始化。这些问题在整理前已存在，不能归因于压缩。

首次续接后另发了一条具体修复反馈，要求修复浏览器加载、地图生成、冲刺、两个存档槽和回放。后续修复与首次交接效果分开记录，不能把收到反馈后的结果冒充为首次自动续接成功。

## 使用方式

在服务器chat_ai根目录，用该项目Python环境执行：

```bash
python skills/context-handoff/scripts/handoff.py prepare \
  --project . --session SESSION_ID --workspace workspace/GAME \
  --out experiments/RUN/snapshot.json

# 让原会话读取SKILL.md和清单，把计划写入plan.json。

python skills/context-handoff/scripts/handoff.py pack \
  --snapshot experiments/RUN/snapshot.json --plan experiments/RUN/plan.json \
  --task-file experiments/RUN/continue.txt --out experiments/RUN/bundle.json

python skills/context-handoff/scripts/handoff.py start \
  --project . --bundle experiments/RUN/bundle.json \
  --out experiments/RUN/target-session.json
```

prepare要求原会话空闲；pack不创建会话；start才创建新ID。脚本不静默删减超预算内容，计划不合法时直接拒绝。恢复已确定的交接结果使用bundle，不重新执行整理。当前实验仅支持文本主会话，没有迁移图片附件，也没有改动生产系统的同会话上下文管理。

## 游戏最终验证与本地预览

收到具体反馈后，千问又执行了10次模型调用并正常结束。浏览器加载错误得到修复，页面能初始化并响应等待与Shift方向操作；引擎独立验证仍为5/10通过，没有自动完成全部任务。

浏览器11项检查中7项通过、4项失败，且无页面JavaScript异常：

- 通过：576×384画布、正确默认种子、初始化、Z等待、Shift方向移动、第一存档槽准确恢复、回放导出包含种子与动作。
- 失败：引擎Game.dash接口缺失（冲刺逻辑只写在UI）、存档缺少版本1标记、第二槽位不能正确恢复、存档与回放组合操作后的回放不能还原相同状态。
- 地图仍有芯片占据出生点的问题。自带测试为4/6通过；它们的假设和覆盖范围也有问题，报告没有把这些失败隐藏。

因此，这次实验说明交接和输入持久化机制可行，但摘要准确性与模型持续执行能力尚不足。不能把浏览器已能打开等同于完整游戏交付，也无法从这一个实验单独证明压缩造成了执行问题：整理前已存在测试失败与无效编辑。

下载的是千问收到反馈后的原始产物，没有由Codex另写游戏来替换实验结果。

- 本地目录：`C:\Users\zhongmiao\Downloads\chat_ai_game_20261016_154228`。
- 本地压缩包：`C:\Users\zhongmiao\Downloads\chat_ai_game_20261016_154228.zip`。
- 预览：`http://127.0.0.1:8318`，仅监听本机，无需服务器端口转发。
- 压缩包：10个文件，17052字节。
- SHA-256：`665889bc96323afba96e00780b043c216ebe78114566ff6e72e856ccf0cc8964`，下载后校验一致。
- 本地预览进程PID：22892；进程信息在preview-server.json。

玩法：方向键/WASD移动，Z等待恢复能量，Shift加方向键冲刺；蓝色为玩家，尝试收集3个芯片后到出口。当前地图与部分功能存在上述缺陷，适合作为实验原型查看。

## 后续可改进点（本次未改生产代码）

- 明确区分摘要中的已验证完成、尚未验证和已知失败，避免阶段状态互相矛盾。
- 当前任务应与历史阶段限制明确分开，完整保存原文不能代替正确理解当前执行范围。
- 小文件可以整份保留，大文件片段尽量覆盖完整函数；本次部分截断的文件又被新会话完整读取。
- 减少整理阶段重复读取已有历史，控制整理本身的输入余量。
- edit_file对old与new相同的调用给出明确反馈，有助于发现无效重复；本次只记录该现象，没有修改工具。
