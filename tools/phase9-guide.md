# phase9-guide.md — 阶段9 M 链审计·预注册规则（R10 冻结版 v1）

> 冻结时间：2026-09-10（脚本运行之前）。上位：PROMPT-SPEC-v2 阶段9。

## 〇、名实差异登记（先于一切判定）

- 规格"宏观里程碑链 M0内核推演/M1制图/M2判据固化/M3流程引擎/M4封装/M5自维持/M6自指 + 推演螺旋结构"——`grep -rln "M0.*内核|M6.*自指|推演螺旋|M1.*制图"` 全工作区 **0 命中**【机械事实】。工作区 "M" 编号属其他命名空间：DS 线"机制发现 M1/M2/M3"（大审查/deepseek/结果_结项总报告_完整版.md:109,121,176）、GLM v4.0"M0 放第一位"（大审查/glm/v4.0-3.md:169，判据优先主义）。
- 处理（R3）：M 链按**规格外部框架**逐项对标工作区证据；每项判定∈{达成/部分/未启动/无对应物}且必须带锚点；M 编号不与工作区 M1-M3 混用（引用时写"规格Mk"）。

## 一、规格 Mk × 工作区对标判据（冻结）

| Mk | 工作区对应物（锚点源） | 判定输入 |
|---|---|---|
| 规格M0 内核推演 | SIM 28 轮推演 125+ 实验 + kernel.py（SIM-SUM 版本链、SIM-KERNEL 断言） | 达成性+退出判据§三 |
| 规格M1 制图 | **本考古任务本身**（3,871 断言/173 边/五区/LM）——首张全图 | 本阶段 delta 基线落盘=M1 首圈完成 |
| 规格M2 判据固化 | extractor-guide 固化、MECH-06 显著性判据、两级门、07-L轴定级脚本 | 判据脚本化程度（LM 矩阵 L3 行） |
| 规格M3 流程引擎 | bootstrap v3.9 引擎+两部署实例+REAL 六轮真引擎 | 已验度（L2 已验格=0 为欠账证据） |
| 规格M4 封装 | library-bootstrap skill v1.2、v3.9 发布链、12 外部技能装机 | 发布链锚点 |
| 规格M5 自维持 | 部署实例自演化循环（m-cron 变异引擎） | 两轴模型:47"S1 判断集采集未开跑"=未启动证据 |
| 规格M6 自指 | L8 自指演化层（21/21 测试，task-006）+_l8_lab 沙盒 | 沙盒态、未接主库 |

螺旋位置：规格"M0-M1 循环、地图 delta 收敛为出口信号"→ 判定：**第一圈出口/第二圈入口**（M0 侧 28 轮已跑完，M1 侧首图本任务落盘；delta 曲线自第二圈起才有值，本阶段只立基线）。

## 二、每圈重量趋势（圈1 内分相，机械）

- 相序（阶段1 时间线口径）：SIM（混元 28 轮）→ REAL（衔尾蛇六轮）→ DS（批次+探针）→ PART2/R2（十二轮+批次A）→ KB/DEPLOY（部署与知识固化）→ 审计（本任务）。
- 新机制速率：mechanism-registry 按 first_seen_universe 计数。
- 翻案速率：tree_edges 按 from 端宇宙前缀统计 refutes+contradicts+supersedes 出边数。
- 判读【研判推断】：新机制前重后轻、翻案前轻后重 → 收敛相特征。

## 三、三件套齐备率（机械关键词，语料=mechanism-registry 行 name+evidence_note）

- 判据件命中词：阈值|判据|门|margin|0\.85|0\.90|显著性|账本
- 边界件命中词：边界|条件|限定|前提|需|仅|场景|依赖
- 失效件命中词：失效|反例|未复现|翻案|红线|毒|失败|作废|0 触发|死区|漂移
- 齐备=三件全中；输出 3/2/1/0 件分布 + 齐备率（全 45 与 active 28 两口径）。语料局限（registry 摘要而非全文）如实声明。

## 四、M0 退出判据（三指标，机械）

1. **机制集稳定性**：active 28/45 与"post-SIM 无机制被证伪"（refuted 机制 12 条全部 first_seen=SIM）双口径。
2. **证伪清单增长率**：坟场 52 条按实验宇宙分布（复用 data/phase5-death-causes.csv）——增长率趋零=稳定（判读）。
3. **红队扑空率**：红队族={VERIM 前缀 VERIF-*、REVIEW-*}（冻结清单）；扑空率 = 1 − (该族 refutes 出边数 / 该族出边总数)，从 tree_edges 机械计算。

## 五、DATA-DRIVEN 占比（旋转门预警）

- 口径：现行断言中 source_file=大审查/data-archive.csv 者，quote 含 "DATA-DRIVEN" 占比（对照 LIT-REPLICATE/NARRATIVE-DRIVEN 并陈）。
- 预警判读（不设硬阈值，规格只要求评估）：占比过高→假设来源单一依赖自发数据、地图级换道闸必要性上升。

## 六、delta-baseline.csv（机械快照，本阶段核心交付）

字段：{item, kind(ledger/report/derived), line_count, sha256[:16] 或 值, note}。入快照：claim_ledger/alias_map/tree_edges/lit-ledger/incident-log/ordering-claims/ghost-papers/mechanism-registry/lm-matrix/supersede_log/audit-log + 五区计数（点值+区间）+ 边数口径区间 + IV=0 open 假设数。**未来增量制图与此表机械 diff 得 delta 曲线。**
- 五区计数区间=floor/ceil ×0.795/1.358（phase5-guide §六因子）。
- 边数口径区间：[实证边数（INFERRED=no），全部边数 173]（INFERRED 55 条为推断边的口径下界）。

## 七、脚本与输出

- `tools/phase9_status.txt` → `delta-baseline.csv` + `data/phase9-summary.txt`。
- 报告 `09-M-STATUS.md`（判定全部带锚点；名实差异§〇置顶）。
