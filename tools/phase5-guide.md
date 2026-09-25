# phase5-guide.md — 阶段5 景观五区·预注册规则（R10 冻结版 v1）

> 冻结时间：2026-09-10（分类脚本运行之前）。此后修订=追加 v2 块+旧块标 superseded（同 R7）。
> 上位文件：PROMPT-SPEC-v2.md 阶段5；gate-revision.md §五 硬规则（区间输出/点值区间同现）。
> 数据源：claim_ledger.csv / tree_edges.csv / data/tree-nodes.csv / mechanism-registry.csv /
> incident-log.csv / ghost_list.csv / supersede_log.csv —— 全部只读。

## 一、统计总体（人口口径）

- **现行有效断言 P** = claim_ledger 中 `status ≠ superseded` **且** `claim_id ∉ supersede_log 登记的被替代 id`。
- 预期基数 3,871（=ledger_tool 口径现行 3,938 − 67 superseded-status − 2 supersede_log 行；两组排除集不相交——已用 phase5_preview 实测核对）。
- 分区基数：verified 3,093 / open 702 / refuted 52 / contradicted 24（四区之和必须=P，脚本内机械校验，不平则报错退出）。

## 二、五区机械定义

| 区 | 定义（机械） | 备注 |
|---|---|---|
| 收敛区 | P 中 status=verified 的断言 | 内部按"独立确认层级"分 tier（见§三） |
| 开放前线 | P 中 status=open 的断言 | hypothesis 子集按 IV 排序（见§四）；其余类型计数并陈 |
| 坟场 | P 中 status=refuted 的断言（全列） | 死因归纳按§五关键词表 |
| 矛盾区 | P 中 status=contradicted 的断言 | 并陈三个机械口径：断言 24 / contradicts 边 10 / 机制清单 CONTRADICTION-CANDIDATE 3（MECH-41/42/43） |
| 幽灵区 | ghost_list.csv 全部条目（非断言口径） | 阶段6 将增 ghost-papers.csv，本区届时补计 |

- 分区互斥性来源：single status 字段（verified/open/refuted/contradicted 互斥）。
- "CONTRADICTION-CANDIDATE" 标注在 claim_ledger 无独立列（schema 9 列无 note），凡入矛盾区一律以 status=contradicted 为准；04-diff §四.2 所列盲建同位矛盾候选不并入计数，只在报告中并陈。

## 三、独立确认层级（tier，实验级继承到断言级）

边是实验/宇宙级对象，确认度只能机械计算到实验，断言继承其实验的 tier：

- **tier-1（跨宇宙确认）**：断言所属实验节点 E 存在入边 (X→E, relation ∈ {replicates, extends})，且 universe(X) ≠ universe(E)（universe 取 data/tree-nodes.csv 的 universe 列）。
- **tier-2（同宇宙复现）**：存在同类入边但 universe(X) = universe(E)。
- **tier-0（无入边确认）**：无任何 replicates/extends 入边。
- tier 就高不叠加：有 tier-1 即记 tier-1。tier-1 与 tier-2 计数并陈。
- **宇宙级端点边**（to_id ∈ {SIM, DS, REAL, VERIF}，不在 tree-nodes 实验节点表，共 4 条 replicates 入边）：**不计入任何实验的 tier**（无法归属单一实验），单独列为"宇宙级整体复现边"并陈。
- E 不在 tree-nodes 中（断言实验无节点）→ tier-0。

## 四、开放前线信息价值 IV（机械）

- IV(claim) = 其实验节点 E 在 tree_edges 中的**关联边数**（from_id=E 或 to_id=E 的边数，含全部 relation）。
- 语义：E 上任一 open 假设被证实/证伪，接触 E 的分支（动机/复现/驳斥/版本链）解释全部可能翻转——关联边数是该语义的机械代理。
- 排序：IV 降序 → 该实验 open-hypothesis 条数降序 → claim_id 升序。E 不在边表 → IV=0。
- 报告呈现：hypothesis 子集 Top-30 明细 + 全量落 data/phase5-frontier-ranked.csv。

## 五、坟场死因关键词表（冻结，匹配顺序即优先级）

对每条 refuted 断言的 verbatim_quote 按下表**顺序**匹配，**首个命中**即归因；全不中 → DC-0。
匹配大小写敏感原文子串（工作区为中文文本）。

| 序 | 死因类 | 关键词（任一命中即归此类） |
|---|---|---|
| DC-1 | 换构造/换引擎未复现 | 未复现 · 未在本 · 未在真实 · 复现失败 · 未触发 · 直接复现失败 |
| DC-2 | 人工构造/地形产物 | 人工地形 · 构造所污染 · 构造不成立 · 目标函数构造 · 不可直接采信 |
| DC-3 | 预注册判据/阈值失误 | 按预注册口径证伪 · 阈值先验错 · 判据 a（ · 判据 b（ · 强形式失败 · 不能作为 cap 的证据 |
| DC-4 | 结构前提不成立 | 结构上不可能 · 结构性不可达 · 结构性平坦 · 被结构关闭 · 固定成本 |
| DC-5 | 工件实现缺陷 | 语法检查 · 双反斜杠 · P0 阻断 |
| DC-6 | 工程杠杆错位 | 93% 代码不在解真正的题 |
| DC-0 | 未归类 | （无命中） |

- 已知局限（如实呈现）：关键词表从 52 条 refuted 原文预览归纳而来，属"从数据到规则"的构造，归纳覆盖率在报告中如实给出；DC 归类属【提取事实】，跨类叙事归纳（如"复现失败≠原结论死亡，可能仅条件性"）属【研判推断】并显式标注。

## 六、区间输出（V2 硬规则，因子冻结）

- **下界因子 f_lo = 0.795**：04-diff.md:16 内容级透镜"折算内容覆盖 79.5%"——独立重提仍会覆盖的账本内容份额（保守保留率）。
- **上界因子 f_hi = 1.358**：|A∪B|/|A| = (1,111+1,087−689)/1,111 = 1,509/1,111（04-diff.md:13,19,21 基数）——第二次独立提取可能新增的份额上限。
- 公式：lo = floor(C×0.795)，hi = ceil(C×1.358)。**点值 C 与 [lo, hi] 必须同现**（gate-revision 硬规则 2）。
- 外推假设（必须随区间声明）：两因子在 SIM 簇（48 文件 1,111 断言）实测，阶段5 将其按类别均匀外推到全账本——这是假设不是事实，标【提取事实→外推假设】。
- 对非断言计数（边数、机制数、幽灵数）：不乘因子（对象是全量枚举非提取样本），但引用 04-diff 口径区间处照报。机制数=45（全量清单），边数=173（全量锚定），此二项为【机械事实】不带区间。

## 七、incident 计数规则

- incident-log.csv 第 2/3 行为逐字节重复行（2026-09-10 续跑核验发现，见 progress.md 开工登记）：一切 incident 计数按**唯一行**计（当前唯一事故=1：方法论-01）。R7 不删行。

## 八、输出与命令（入档）

- 分类脚本：`tools/phase5_zones.txt`（py -X utf8 运行）
- 落盘：`data/phase5-zone-assignments.csv`（claim_id,experiment_id,zone,tier,iv）、
  `data/phase5-death-causes.csv`（claim_id,experiment_id,death_cause,matched_keyword）、
  `data/phase5-frontier-ranked.csv`（open hypothesis 全量排序）、`data/phase5-summary.txt`（stdout 重定向）
- 报告：`30-景观五区.md`——所有计数表 = 点值+[区间] 双列；生成命令逐表注脚。
- 分区基数校验失败（≠3,871 或四区之和≠P）→ 脚本 exit 1，不产出报告。

## 九、v2 修订块（2026-09-10 首轮运行后追加；§五关键词表被本块部分 superseded）

- 动机：v1 表对 52 条 refuted 覆盖率仅 50%（26 条 DC-0）；检视未归类样本（data/phase5-death-causes.csv v1 轮输出）后定向扩充一次。此后不再迭代（防无限回炉，精神同 V4）。
- 追加关键词（并入对应类，匹配仍取首个命中）：
  - DC-1 追加：`冷启动失败` · `真实库冷启动`
  - DC-3 追加：`REFUTED`（全大写逐字——PART2 预注册裁决表行/红队行）
  - DC-4 追加：`被否决`
- 新增 **DC-7 机制零效应/无效**：`与预期相反` · `完全无效` · `几乎无差` · `无收益` · `该形态阴性` · `未确认超线性` · `全败`
- 匹配顺序更新：DC-1→DC-2→DC-3→DC-4→DC-5→DC-6→**DC-7**→DC-0。
- 已知结构局限（不修订、如实呈现）：refuted 的 hypothesis 行其 verbatim_quote 是**假设原文**而非死因叙述（死因在驳斥它的边/后续实验里）——此类行保持 DC-0，报告按 claim_type 交叉呈现。
- 实现载体：tools/phase5_zones.txt 的 DEATH 表同步本块（v2）。
