# constants-registry.md — 冻结常数登记簿（20260919 VKPS 评估卷结论三/ROI 第二件，本区自实践）

> 评估卷结论三：append-only+冻结+不追溯叠加后，被更正的输入永远无法传播进派生常数。
> 修法=区分「冻结判定」（不可变）与「冻结常数」（值可不改，**必须携带可执行配方+
> 输入勘误标志位**）。本簿即后者：每个常数一条记录，值不改、标志必亮。
> 维护纪律：新常数入簿须带配方与输入锚；输入被勘误时**追加 STALE-INPUT 行**（不改旧行）。

| name | value | recipe | inputs | 状态 |
|---|---|---|---|---|
| f_lo（有效断言下界因子） | 0.795 | 内容覆盖折算（04-diff 内容级透镜） | 04-diff.md:16 内容覆盖 79.5% | 现役 |
| f_hi（有效断言上界因子） | 1.358 | (A + B − M) / A | A=1,111@04-diff.md:13 · B=1,087@:19 · M=689@:21 | **⚠ STALE-INPUT**：A 已于 b-plan/REPORT.md:10-14 裁定为登记层笔误（正确值 1,098）；重算值 1.3625（未采纳，值仍冻结，差 0.33%） |
| 包含度阈值（CORE 匹配） | 0.60 | 短串被长串包含比例≥0.60 | intersection_core.py:44（主匹配器 Counter 交集/min）/ core_expand_c5.py:39-43（扩核 difflib 版）——**两实现并存在案**（评估卷弱项⑪），对账归口=主匹配器 | 现役（双实现注记） |
| 行差容差（CORE 匹配） | ±3 | |location_anchor 行 − 提取行| ≤3 | intersection_core.py:40 | 现役 |
| 抽检命中率门 | 0.80 | hit/total ≥ 0.8 → exit 0；**total=0 → exit 1**（20260919 修，原空输入 exit 0=探针已死） | tools/ledger_verify.txt:74 | 现役（已修） |
| 实验宇宙口径 | 剔 CBB | effective(status≠superseded) − count(experiment_id~^CBB) | 037/038/055 裁决链，INCREMENTAL-LOG:973-982 | 现役 |
| claim_id 幂等键 | 两代并存 | v1（数据行 1-3,940）=sha256(f\|line\|quote[:80])；v2（3,941+）=sha256(f:line:quote[:80]) | ledger_tool.txt:24-26 / merge_claims.py:62 | **⚠ 跨代不互通**（评估卷弱项⑧）：append2.py 已改双代键查重（20260919），keygen 列未加（账本零改写优先） |
| EXCL 排除模式 | 20 个 | scan2b.py:20 元组 | 逐模式排除计数**未产出**（评估卷弱项⑫，PRISMA 建议） | ⚠ 待补计数 |
