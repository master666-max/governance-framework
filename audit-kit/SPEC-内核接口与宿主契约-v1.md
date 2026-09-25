# 规范 · 内核接口与宿主契约 v1（2026-09-23，审计区）

> 依据：《架构备忘-自由模块化与五问》问③——三份规范正式化，解锁多宿主/
> 自由模块化（blender-kb 等小库自由选择微内核或大内核、可迁移）。
> 性质：**接口规范**（说什么算符合），实现见各内核（audit-kit+memsys=重装
> 形态；evo-seat/evo_seat.py=融合形态）；**一致性测试**=`audit-kit/conformance.py`。

## §A Governance Surface（治理面规范——内核向上提供什么）

任何内核必须提供以下符号（签名级）：

| 符号 | 语义 | 强制度 |
|---|---|---|
| `open(path)` | 建/开库（幂等）+开库即验（G1+） | 必须 |
| `append(actor, kind, payload)` | **唯一写入口**；链哈希 v2（actor/kind/payload 并入） | 必须 |
| `verify()` | 链重放 + 触发器在位；任何不一致抛错 | 必须 |
| `count()` / `head()` | 事件数 / 链头哈希 | 必须 |
| 触发器 `no_update`/`no_delete` | UPDATE/DELETE 物理 ABORT | 必须 |
| `meta['schema_version']` | 版本协商键在位 | 必须 |
| `anchor(库)` | 链头入库外锚物 | G5 |
| `scan(目录)` | 出站引用三态扫描 | G5 |
| 能力令牌四关 | NO_CAP/SCOPE/CANNOT/EXPIRED | 重装形态必须；融合形态=档位静态权限（豁免声明） |

## §B Host Contract（宿主契约——宿主向下要做什么）

宿主（记忆库/技能经验库/任意知识库）只做三件事：

1. **域逻辑纯函数**：条目的打分/衰减/生命周期扩展——不碰账本（账本归内核）；
2. **kind 注册（声明式）**：`kinds.yml` 或内联字面集——每个 kind 含
   description/actor_pattern/authority_level；
3. **判据注入（预注册）**：`prereg/*.md`——金标判据（何为 irreversible/
   阈值/ground truth 标法）先于实现冻结。

宿主**不得**：自建账本、绕过 append 直写存储、在域逻辑里做治理决策
（晋升/合并/冲突判定走内核 decide 面）。

## §C Kernel Interface（内核接口——宿主面向什么编程）

宿主代码只许依赖以下抽象（不依赖具体内核实现）：

| 抽象 | 方法 | 说明 |
|---|---|---|
| `LedgerLike` | open/append/verify/count/head/rows | 换内核不换宿主代码 |
| `AuthorityLike` | adjudicate(intent, entries) + trace 结构 | 银标挣得机器接口 |
| `ScannerLike` | scan_refs(dir) -> 三态列表 | 出站扫描 |
| `EVO_STATES / TYPES` | 常量集 | 三态/类型枚举跨内核一致 |

**版本协商**：宿主读 `schema_version`；内核升 schema 须提供迁移或双读。

## §D 跨形态语义一致性（硬性——哪个形态都不能松）

1. append-only 物理强制（触发器 ABORT，非应用层约定）；
2. 链哈希 v2（actor/kind/payload 并入——头部字段篡改可检出）；
3. 墓碑=退出检索+原位保留（无"删除"状态）；
4. fail-closed（缺件抛错，含"既有库先验触发器"）；
5. 决策留痕结构（intent/entries/decision/rationale/severity_if_wrong）。

## §E 一致性测试（conformance）

```
py -X utf8 audit-kit/conformance.py --kernel audit-kit --host memsys   # 重装形态
py -X utf8 audit-kit/conformance.py --fused evo-seat/evo_seat.py               # 融合形态
```
检查 §A 符号 + §D 语义（对临时库实跑：触发器 ABORT/墓碑/链 v2）+（给
--host 时）§B 三件事在位。全过 exit 0；任一 FAIL 输出证据行。

## §F 副本对账（合并形态的必备件——问④）

融合/旁挂形态的框架副本自带 `framework_sha`（段哈希或文件哈希），
`verify` 顺带输出；宿主项目应定期与权威版对账（T-E 防御：k 份副本差集
静默，**无对账的合并才是问题**）。

---
*审计区规范件 · 2026-09-23 · v1；实现见 audit-kit/memsys/evo_seat；*
*变更走修宪程序（判据先于实现）*

## §G 注入面（条目怎么进库 · 2026-09-23 追加）

**设计原则：内核管好"入库门"，不管"采集"——采集器外置，产出经统一交换
格式进门。** 采什么、从哪采是宿主/管线的事；进门必须走同一条受检通道。

### 大框架侧（全体系）的注入途径盘点

| 途径 | 实现 | 把关 |
|---|---|---|
| 引擎吸收（md/pdf/csv/json 批量） | C-1 结构化吸收器（已关单） | 转换层+管线守恒 |
| 旧知识迁移 | migrate（先登记指纹） | 存量基准锚 |
| 会话挖掘（对话增量回灌） | session-mining 管线（599 条实证） | 双盲提取+自检 |
| 网络收集 | web-collector（三硬约束） | 分级+注入防御+open 上限 |
| 自主捕获 | capture-inbox（三问判据） | 暂存区+管线回灌 |
| 定时同步 | m-cron 每日窗口 | 同上 |
| 审计动作（验收/裁决） | 账本+LOG | 人侧验收 |

### 微内核侧（evo-seat）的注入面

**两个入口，一道门**：

1. `append`（单条）——交互/agent 直用；
2. `import <库> <file.jsonl>`（批量）——**批量≠放宽**：逐行构造校验（G2+）、
   content_hash 幂等去重、坏行计数拒——全走 append 留痕（actor=
   `import:pipeline`）。

**JSONL 交换格式**（外置采集器 → 内核的标准界面）：
一行一条目 `{"id","content","keywords?","importance?","type?","source?"}`——
C-1 吸收器/网络收集/会话挖掘的产出转成本格式即可注入**任何内核**
（融合/重装同吃）。

**缺口与边界**：微内核**不内建**各种吸收器（保持单文件小）；需要批量采集
时，用外部工具产出 JSONL 再 `import`——采集器生态在外，入库门在内。
