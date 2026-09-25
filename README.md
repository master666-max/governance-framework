# AI 可信治理框架 · 模块发布

> **本仓是模块发布面（公开）**：治理核 + 演化核 + 记忆库 + 微内核 + 装配器 + 门面。
> 纯 Python 标准库，**零第三方依赖**；各模块自带 unittest 测试套件。
> 模块间关系取自 2026-09-25 的实测测绘（AST 依赖边 320 条 + Tarjan 环检测）。
> 深入阅读：`ARCHITECTURE-定版v1.0-20260923.md`（概念总纲·冻结清单）→ `架构图-20260923.md`（完整架构图：两轴×三产品×一码四包）。

## 〇 · 一张图先立骨架

```
                ┌──── 治理核 audit-kit ────┐       ┌──── 演化核 evocore ────┐
                │ 账本·凭证·预注册·符合性  │       │ 检索·生命周期·决策·指纹 │
                └───────────┬──────────────┘       └───────────┬────────────┘
                            │   ┌──── 记忆库 memsys ─────┐     │
                            └───│ bridge = 双核装配示例  │─────┘
                                └───────────┬────────────┘
                                            │ 源码
                    ┌─── 装配器 build（assemble.py：一码四包）───┐
                    │ 微内核(evo-seat) / 中库(kb) / 独立包(pypkg) / 共库(server)
                    └────────────────────┬──────────────────────
                                         │
                门与对账 tools/（治理门·质量门·对拍器·副本闸——检验上面所有人）
```

## 一 · 双核（体系的地基，互不 import——这是设计不是巧合）

**`evocore/`（演化核）**：管"**记忆怎么活着**"。`entry.py` 的 `content_hash` 是全体系唯一
指纹来源（64 位 hex，排除 id/state 等易变字段；规则钉在 `build/tests/test_content_hash_divergence.py`）；
`lifecycle.py` 状态机（ACTIVE→ATTIC→TOMBSTONE，只迁移不销毁）；`retrieval.py` 检索打分；
`decision.py` 决策规则；参数全部外置（tunables，版本可协商）。

**`audit-kit/`（治理核）**：管"**谁被允许做什么、做了必留痕**"。`ledger/ledger.py` 是
append-only 链账本（BEGIN IMMEDIATE 事务化、触发器物理禁 UPDATE/DELETE、开库即验链）；
`core/gov_types.py` 是能力令牌 `Capability`（can∩cannot 构造即拒）；`core/prereg.py`
预注册判据；`boot_self.py` 用自己的账本记自己的提交。

**关系**：evocore 不知道 audit-kit 存在，audit-kit 不 import evocore。唯一交点是那个
指纹函数——记忆内容的完整性由治理侧可验证，但两侧代码零耦合（"执行并集、证据不同根"）。

## 二 · memsys（双核的活体装配示例）

`bridge.py` 同时 import `audit-kit/core`（Capability、Ledger）与 `evocore.entry`
（content_hash），把两核粘成一个可用的记忆库——证明"双核可装配"不是图纸。改任一核，
bridge 和它的测试立刻知道。`kinds.yml` 声明记忆类型注册表，与 `bridge.KINDS` 的对拍由
`tools/tools_crosscheck.py` 执行。

## 三 · build（装配器：一码四包）

`assemble.py` 从同一份双核源码机械产出四种形态：`fused`（单文件微内核）/ `vendored`
（中库自足包）/ `pypkg`（pip 独立包）/ `server`（L2 共库，`l2server/server.py` 为 MCP
服务件）。`tests/` 是全体系最重的裁判（131 测）；`manifests/` 登记产物哈希供发布对账。

**关系红线**：assemble 按路径+字符串模板镜像源码——**改双核文件必须同步装配器**，
否则发布树静默漂移。

## 四 · tools（门与对账面——体系的免疫系统）

不在生产数据流里，专门检验别人：`hooks/pre-commit`（治理门：append-only / LOG 撞号 /
SOP 副本一致性 / R2 不可证伪面四查）；`invariant_scanner.py`（R2 判据）；
`code_quality_gate.py`（五查质量门）；`tools_crosscheck.py`（双包对拍）；
`check_vendored_copies.py`（副本族逐字节闸）；`README-工具面状态.md`（登记表）。
与 evocore 的关系是单向消费者（验证时导入它）。

## 五 · skill（发布面）

把体系装进"能发给别人"的壳：`SKILL.md` + 安装脚本 + `migrate.py` 等自足副本
（由 `tools/check_vendored_copies.py` 上闸——vendored 副本不是病，**漂移**才是，
所以闸的是一致性不是重复）。

## 六 · 一次真实写入的数据流（把上面串起来）

宿主 agent 调 `memsys.bridge.MemoryLedger` 写一条记忆 → bridge 先问
`audit-kit.gov_types` 要凭证（无凭证即拒）→ `evocore.entry.content_hash` 算内容指纹
（去重与完整性锚）→ `audit-kit.ledger` 以 BEGIN IMMEDIATE 把事件追加进链（含
prev_hash 衔接）→ 写毕，`tools_crosscheck` 可对拍双库同链，`invariant_scanner` 与
质量门保证改行为有据。

## 七 · 一句话收束

**evocore 管记忆的生命，audit-kit 管行为的账，memsys 证明两者能装在一起，
build 证明能装成四种形态，tools 负责怀疑一切。**

## 测试

各模块自带 `tests/`（unittest，纯标准库即可跑）：
`py -X utf8 -m unittest discover -s tests -q`（在对应模块目录下执行）。

| 套件 | 独立运行 |
|---|---|
| evocore 78 测 / audit-kit 54 测 / memsys 17 测 | ✓ 全绿——三核完全自足 |
| tools 11 测 | 差 1：副本族校验器的"真仓常态断言"依赖完整工作区的副本族布局 |
| build 131 测 | 活体门套件——依赖完整治理工作区（账本/增量 LOG/工作区路径），在全量仓里全绿；本仓按源码呈现 |

即：**三核自足**；build 与 tools 是"检验别人"的活体门，本就设计为在完整工作区里运行。
