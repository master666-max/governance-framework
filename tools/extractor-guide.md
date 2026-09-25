# 提取员指南（阶段2 断言提取·子代理必读 v2）

> 本文件是 workspace-audit 阶段2 的**持久化提取提示词模板**（2026-09-10 固化，
> 修复交接期模板仅存于会话历史的问题）。任何提取子代理开工前必须先读本文件全文。

## 你的任务

对指定的源文件清单逐文件提取**实验性断言**，产出 JSONL 中间清单。
主会话随后用 `tools/ingest_extract.txt` 程序化入账并用 `tools/ledger_verify.txt`
逐字复核——锚点不精确的条目会被**整条拒绝**，所以锚点精确性高于一切。

**铁律：源文件只读（R1）。你唯一可写的文件是你的输出 JSONL。**

## 输出格式

`workspace-audit/data/extract/<批次名>.jsonl`，每行一个 JSON 对象：

```json
{"file": "大审查/xxx/yyy.md", "line": 3, "start_anchor": "X0 PASS（7.5 秒", "end_anchor": "10/10 步全过）。", "claim_type": "result", "experiment_id": "REAL-X0", "source_type": "document", "status": "verified", "note": "环境自检10步全过"}
```

字段：
- `file`：工作区相对路径，**正斜杠**分隔，与清单逐字一致
- `line`：整数。**Python `readlines()` 的 1-based 行号**。
  ⚠️ Read 工具的行号在 `\r\r\n` 行尾文件上会漂移——写完必须跑自检脚本核对
- `start_anchor` / `end_anchor`：该行内**逐字存在**的子串；摘录=从 start_anchor
  开头到 end_anchor 结尾（含两端）的闭区间；总长 ≤200 字；end_anchor 必须出现在
  start_anchor 之后；锚要选有区分度的片段（不用"的""。"这种到处都是的）
- `claim_type` ∈ `hypothesis`(假设/预测/预注册判据) / `method`(机制/流程/设计)
  / `result`(实测数据/运行结果) / `verdict`(结论/裁决/证实证伪) /
  `parameter`(数值参数/hash/版本号)
- `experiment_id`：宇宙前缀制，见下表
- `source_type`：`document`(结构化报告/笔记) / `dialogue`(会话导出/聊天记录)
- `status`：`verified`(文内或引证证据成立) / `refuted`(文内明示证伪) /
  `open`(悬而未决/待验) / `contradicted`(多版本冲突) / `superseded`(被后续版本修正)。
  该断言在**写下的当时**的状态；拿不准用 open
- `note`：≤30字 提取理由，仅供人读，不入账

## experiment_id 前缀表（与已入账 1,620 条保持一致）

| 前缀 | 宇宙 | 示例 |
|---|---|---|
| SIM- | 混元离线推演 | SIM-E81、SIM-R07（第7轮） |
| REAL- | 衔尾蛇真引擎沙盒 | REAL-X0、REAL-总树 |
| R2- / R2A- | 第二批推演（zcode） | R2A-T2-1 |
| DS- | DeepSeek 线 | DS-R1-1、DS-R2-N2 |
| PART2- | 大审查 PART II 假设循环 | PART2-H-R1-1、PART2-OBL-003 |
| VERIF- | 猴子记忆库对抗验证 | VERIF-A1 |
| DB- | 豆包（agora/memevo/v4工单） | DB-AGORA、DB-MEMEVO、DB-V4 |
| CB- | codebuddy 交接 | CB-MEMEVOLVE |
| GLM- / QWEN- | 网页端GLM / qwen 工单 | GLM-WO-v3.8、QWEN-v4.0 |
| REVIEW- / SYN- | 复审 / 统合报告 | REVIEW-GLM、SYN-README |
| PLAN- | 规划书类 | PLAN-H3 |
| KB- | knowledge 主库线（本次新增） | KB-P001、KB-PT006、KB-D003、KB-TASK-013、KB-INDEX、KB-REFLECT |
| PART1- | 四轮外部审查链（trajectories task-009~012） | PART1-Z014 |
| RADAR- | sota-memory-radar 文献雷达 | RADAR-SOTA |
| L8LAB- | _l8_lab 实验线（本次新增） | L8LAB-CONSTITUTION、L8LAB-MUT |
| DEPLOY- | 库调试部署线（本次新增） | DEPLOY-V32、DEPLOY-V39、DEPLOY-S0 |
| META- | 根级元文档（本次新增） | META-HANDOVER、META-AGENTS、META-FREEZE |

## 提取什么 / 不提取什么

**要**：实验结论与数字判据、机制描述、预注册假设、裁决（证实/证伪/翻案）、
版本号、引擎/内容 hash、参数值（权重/阈值/预算）、事故与死因、
跨宇宙引用（谁复现了谁、谁推翻了谁）。

**不要**：目录/导航文字、纯日期签名、寒暄、AI 自评性空话（"我觉得这很重要"）、
同一断言在同文件重复出现只取首处、模板样板文字（引擎包 install/SKILL 样板）、
正文之外的 YAML/HTML 标记。

**csv 文件**（meta_log/data-archive 等）：数据行本身即断言，line=该数据行的
物理行号（表头是第1行），锚点取行内关键片段。

**版本对文件**（同名多版本）：各版本分别提取，摘录各版本**差异处**与结论行；
版本间结论不同 → 各自标 status 并对旧版标 `superseded`（新版本的对应行）或
`contradicted`（无法定序时）。

## 密度基准

参照已入账批次：普通报告 8~15 条/文件；短说明 3~5 条；大型总报告 20~40 条。
宁缺毋滥，但**关键结论/hash/判据数字一条不能漏**。

## 提交前自检（必做，不过不许交）

```
py -X utf8 "D:\zcode专用！！！！危险！！！！！！！！！\workspace-audit\tools\extract_check.txt" data/extract/<批次名>.jsonl
```

全 PASS 才算完成。FAIL 的条目修锚点或删条目后重跑。

## 完成后汇报格式

主会话只需要：批次名、文件数、断言条数、自检结果（PASS n/n）、
以及你做过的分类判断（≤5条，如"X 按 method 入账因原文为将来时"）。
