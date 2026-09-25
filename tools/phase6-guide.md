# phase6-guide.md — 阶段6 文献全摄入·预注册规则（R10 冻结版 v1）

> 冻结时间：2026-09-10（构建脚本运行之前）。上位：PROMPT-SPEC-v2 阶段6 + R4/R5 铁律。
> 本阶段不改 claim_ledger（文献摄入走独立 lit-ledger；两轴模型既有断言已由 deploy 批次入账 22 条，不重复）。

## 一、文献源（冻结范围 S1-S7）

| 代号 | 文件 | 角色 |
|---|---|---|
| S1 | `引用论文总表.md`（根，193 行） | 33 篇总索引**原版**（正文实列 31，漏 A4/A10） |
| S2 | `library-bootstrap-v3.0/review-20260908/引用论文总表_修订版.md`（212 行） | 修订版（补 A4/A10 + T1/T2/T3 落地层级）；**每纸主行取此版**（版本号最高者优先） |
| S3 | `knowledge/references/sota-memory-radar.md`（67 行） | 雷达自产综述（21 条目/七派） |
| S4 | `库调试工作区/citations.md` | 引擎题录（REGISTRY 渲染；含 8 条自注） |
| S5 | `library-bootstrap-v3.0/review-20260908/论文实现核对报告.md`（139 行） | 机器核对报告（T4 九条、B1-B7） |
| S6 | `库调试工作区/references/两轴模型与演化授权-v1.md`（48 行） | L/E 双轴框架（ordering 主源） |
| S7 | `knowledge/skills/library-bootstrap/SKILL.md` | 建库技能（档位阶梯行） |

版本链（S5:11 与 S2:7-12 逐字为据，登记不裁决）：S1（原版）→ S5（v3.8.1 核对，T4=9）→ v3.8.2/L9-DELIVER 补丁 → S2（修订版改判 A24/A29/A32/A33）。**阶段1 遗留项"原版 vs 修订版差异"就此了结**：差异=补 A4/A10+落地层级+名实修正，同属旧33体系的版本演化，不是"新批次"。

## 二、lit-ledger.csv schema（spec 字段为必含最小集，下为超集）

`lit_id, paper_id, batch, source_file, anchor, verbatim_quote, row_type, mechanism_type, testability, external_claim_numbers, status`

- **lit_id** = sha256(paper_id+anchor+verbatim_quote[:80])（幂等，R7 同构）
- **batch** ∈ {旧33, 雷达综述, 新批次}——**新批次本轮 0 行**（00-文献清单 §四：无实体；解释③原版vs修订版已证伪为版本演化）
- **row_type** ∈ {简介, 落地, 雷达判定, 题录自注, 核对结论, 核对问题, 原版用途}
- **status**：默认空；S5 中被 v3.8.2 补丁改判的四纸行（A24/A29/A32/A33 的 T4 判定）标 `superseded-by-patch`（依据=S2:11 逐字）

## 三、提取区（冻结；区外文字=叙事性主张丢弃并机械计数）

1. **S2 每纸 2 行**：`- **简介**：`行（row_type=简介）+ `- **落地**：`行（row_type=落地）→ 33×2=66 行，batch=旧33
2. **S3 七派表体行**：`|`开头且非表头/分隔线的 21 行（row_type=雷达判定，batch=雷达综述）
3. **S4 自注 8 行**：`- **A\d+** … — 注文` 的注文段（自"— "起逐字切片；row_type=题录自注，batch=旧33）
4. **S5 三区 12 行**：§一 4 条结论（20-23 行，row_type=核对结论）+ §2.2 B1-B7（row_type=核对问题）+ :87 T 计数行（核对结论）
5. **S1 7 行**：名不副实七纸（A1/A5/A8/A12/A14/A18/A19，名单=S2:10 逐字）的 `- **库中用途**：`行（row_type=原版用途，batch=旧33）

- **丢弃计数口径（机械）**：丢弃行数 = (S1∪S2∪S3∪S4∪S5 非空行数) − (上述提取区命中的去重行数)，脚本输出，不逐条列出。
- **摘录硬规则**：verbatim_quote = 命中行（或切片）的**前 200 字符硬切**（不加省略号、不加任何非原文字符）；脚本逐行 assert 摘录∈原文行。

## 四、mechanism_type 分类表（冻结，33 纸逐一映射）

A派-分层记忆OS：A1,A14,A16,A18 ｜ B派-管线抽取：A12,A19,A27 ｜ C派-图/联想检索：A8,A9,A11,A15 ｜ D派-认知架构/反思：A2,A3,A4,A5,A10,A23 ｜ E派-生物启发/遗忘/睡眠：A6,A13,A20 ｜ F派-长上下文压缩：A17 ｜ G派-产品实践：A26,A28 ｜ 自进化/自指：A21,A22 ｜ 认知科学经典：A29,A30,A31,A32,A33 ｜ 上下文工程/技术报告：A25 ｜ 综述参照：A7 ｜ 用户内部文档：A24
（S3 行按所在派赋同表；S4/S5/S1 行继承该纸映射；元行〔核对-总表〕=题录核对）

## 五、testability 映射（冻结）

S2 落地层级前缀 `T1*`→Y（代码/文件层可复测）；`T2*`→Y（流程层 skill 可复测）；`T3`→N（未实现，无可测对象）；**例外表（RL 核心，覆盖前述规则）：A17、A19 → 需权重访问**。S3 雷达行：判定含"已吸收"→Y，"观察/不适用"→N。S4/S5/S1 行：继承该纸 S2 映射（元行=空）。

## 六、external_claim_numbers（冻结正则）

对命中行的**整行**跑三个逐字模式，命中子串以"；"连接入字段（空=无自报数字）：
`\d+(?:\.\d+)?%(?:\s*→\s*\d+(?:\.\d+)?%)?`（百分比/箭头对）、`\d+(?:\.\d+)?x`（倍数）、`3\.5M`（MemAgent 专属字面）。
全部按 R4 标 EXTERNAL-CLAIM 语义：**只登记不采信**（字段名即标记；06 文档再声明一次）。

## 七、ordering-claims.csv（冻结 8 行）

`claim_id, source_file, anchor, verbatim_quote, ordering_type`
- S6:14 核心命题行（ordering_type=跨轴禁则）
- S6:20 E0 行、S6:21 E1 行、S6:22 E2 行、S6:23 E3 行、S6:24 E4 行（E1-E4=**E链前提**；E0=L↔E映射）
- S6:26 通用红线行（跨轴禁则）
- S7:3 档位阶梯行（"8 档预设（L0 裸奔 → L7 实验）"，ordering_type=能力阶梯）
摘录同 §三 200 字符硬切+assert。

## 八、ghost-papers.csv（冻结 34 行）

`paper_id, name_token, type, cited_in_anchors, fulltext_in_workspace, note`
- A1-A23、A25-A33（32 条）：fulltext_in_workspace=**N**（00-文献清单 §五：0 论文 PDF/全文；type=论文/经典/官方文档/技术报告按 S2 来源行）
- A24：fulltext_in_workspace=**Y(提取本)**——attic/_bca_extract.txt 在位；原始 doc 形态未考（note 注明）
- RADAR-X1（Anthropic memory tool，S3:55）：type=官方文档，N（雷达独有，不在 33 系统内）
- **R5 红线重申**：以上无原文条目的一切内容，禁止用训练记忆补充；lit-ledger 中它们的"内容"仅限 S1-S5 中实际存在的文字。
- cited_in_anchors：程序化收集（S2 简介行锚点为主锚 + S3 行锚点若有）。

## 九、输出与命令

- 构建脚本：`tools/phase6_build.txt` → `lit-ledger.csv` / `ordering-claims.csv` / `ghost-papers.csv` / `data/phase6-build-log.txt`
- assert 全过（逐字+≤200）才落盘；任一 assert 失败 exit 1 且不产出。
- 分析文档：`06-新旧文献交叉.md`（人工撰写，含重叠/互补矩阵+LIT-gap 登记，全部锚点引用）。
- 收尾抽检：新入账 lit 行取 lit_id 尾数逢 7 者回原文核对（audit-log 登记 phase=6）。

## 十、v2 修订块（2026-09-10 构建首跑后追加）

- §三.3 修正：S4 题录自注**实测 10 条**（A14/A16/A17/A21/A22/A25/A27/A28 **+ A31/A33**——初版 guide 依 head -30 预览误计 8）；提取规则不变（含 ` — ` 注文行全取），仅计数断言 8→10。lit-ledger 总数相应 116 行（66+21+10+12+7）。
