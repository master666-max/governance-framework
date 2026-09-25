# 工具面状态登记（tools/ · 2026-09-23 · W2 批新建）

> **为什么要有这件**：`tools/` 88 个跟踪件里，**42 个已退役但看起来还活着**（输入数据的工作区已改名/迁走，
> 脚本里写死的路径全废），另有 **104 个仓内 Python 以 `.txt` 存在**（本目录 43 个）曾结构性绕过
> pre-commit 的 R2 闸门。此前无任何一处登记"哪些工具还能跑、哪些不能、不能的原因是什么"——
> 于是「跑不出结果」与「跑了没问题」在读者眼里同形。本件即该缺口的处置（登记，不改写退役件本体）。
> **纪律**：退役件**不得当仪器引用**；需要复算历史读数时，必须先按当时输入重建环境，否则读数无指称。

## 一 · 三态分类（现值 89 件全覆盖；建件时 88，本批 +1＝`publish_reconcile.py`）

> **20260925 复核勘误**：tools/ 复核后现值 **92 件 / 28 .py**，较建表 +3/+2（新增含 `test_code_quality_gate.py`、`check_vendored_copies.py`），新件未重新分类；逐件定活复核见 `_refactor-kit/LIVE.md` §2。

| 态 | 件数 | 判据 | 处置 |
|---|---|---|---|
| **活 · 自足可跑** | 18 | `.py`（25 顶层 + `skill-installer/migrate.py`，扣掉下面 8 件需外部路径的），路径由 `__file__` 自定位 | 可直接跑；改动走质量门 |
| **活 · 需显式传参** | 8 | `.py`，依赖**仓外**工作区（主区/大审查/DSH 部署位） | 必须传参或设环境变量；**缺参即 fail-closed 退出**，不猜路径 |
| **退役 · 输入已不存在** | 43 | `.txt` 形态的阶段管线（phase4-11 / touchstone / spotcheck / tree / build_*） | 只作历史证据保留；**不得引用其读数** |
| **非代码件** | 20 | 导则/台账/模板/安装脚本/钩子（`.md`/`.csv`/`.sh`/`hooks/`） | 各自有归属，见 §六 |
| 附：纯文本台账 | 1 | `tools/smell-baseline.txt`（首行非编码声明，故不被门误纳） | 坏味豁免台账（计入上「非代码件」20 内） |

**退役 43 件的两种死法**（都可复算）：
- **42 件**写死已废盘符 `D:\zcode专用！！！！危险！！！！！！！！！`（工作区已改名/迁走）；
- **1 件** `find_lit_files.txt` 用旧工作区**相对路径** `workspace-audit/data/files.jsonl`——该目录名已不存在
  （现值 `data/files.jsonl`），故同样跑不动，只是死法不同（相对路径漂移，非绝对路径失效）。

复算：
```bash
cd D:/zcode-workspace-audit
git ls-files tools | wc -l                               # 91（20260925 复核实测；建件时 89）
git ls-files tools | grep -c '\.py$'                     # 27（20260925 复核实测；建件时 26）
grep -l 'AUDIT_NEST\|AUDIT_MAIN\|DSH_SKILL_DIR' tools/*.py | wc -l   # 8（需外部路径）⇒ 自足 26-8=18
git ls-files tools | grep -c '\.txt$'                    # 44（=43 退役 Python + 1 纯文本台账）
grep -lI 'zcode专用' tools/*.txt | wc -l                  # 42（退役之死法一：写死废盘符）
for f in tools/*.txt; do head -n 1 "$f" | grep -q '^# -\*- coding' && echo x; done | wc -l   # 43（.txt 形态 Python）
```

## 二 · 活 · 需显式传参的 8 件（W2-N8 已改 fail-closed）

| 件 | 传参方式 | 缺参/路径不存在的现行为 |
|---|---|---|
| `verify_hy_pb2.py` | `argv[1]` 或 `AUDIT_NEST` | `SystemExit` + 用法提示（rc=1） |
| `verify_kernel_t15_best.py` | 同上 | 同上 |
| `verify_doubao_anchor.py` | 同上 | 同上（原 `glob(...)[0]` → IndexError） |
| `verify_doubao_e94.py` | 同上 | 同上 |
| `verify_t1_hy.py` | 同上 | 同上 |
| `artifact_verify.py` | `AUDIT_MAIN`（可选根） | 未提供→**stderr 明报覆盖面缺口**并继续（原为 `os.path.join(None,…)` TypeError）；提供但不存在→rc=1 |
| `ledger_audit.py` | `AUDIT_MAIN`（可选根） | 未提供→基线段明报「指向主区的锚计入 FILE-MISS，**属覆盖面缺口不是引文腐烂**」 |
| `survey_manuals.py` | `AUDIT_MAIN` + `DSH_SKILL_DIR` | 该位置记为 `<位置不存在>`（原逻辑已具备，本批只去掉写死值与本机用户名路径） |

**改前病灶**（两类，都已实测）：
1. 写死 `D:\zcode-workspace-audit`（11 件 `.py`）→ 换机/改名即失效；本批全部改为 `__file__` 自定位，
   逐件真值检查 11/11 解析到仓根（复算见 `开工-20260923/02-自检读数.md`）；
2. 靠 `glob`/`os.listdir("D:/")` **猜**外部工作区（5 件）→ 猜不中的报错形态（IndexError/TypeError/JSONDecodeError）
   完全看不出「是路径没了」，属"什么都没查"伪装成"查了失败"。

## 三 · 时点验收器（跑得出结果、但结果已无指称）

| 件 | 基准 | 现状 | 处置 |
|---|---|---|---|
| `S1_verify_src.py` | S1 平移前 `b19c9a4`（层1：源件逐行等价 + 白名单 W1=3/W2=4） | **必判红**：S1v2（`b0da6bb` 条目197）有意改了 tunables/retrieval/lifecycle/decision ⇒ 实测违例 33（7 行自带 `S1v2/T1-T2` 标记）。工具本身末次改动在 `47a477d`（条目194 S1 交付），**S1v2 之后无人复跑** | 保留为 **S1 时点验收证据**；现役的行为面判据换成 `S1_verify_behavior.py`（层3：33 用例差异 0，2026-09-23 W3 批实跑 PASS）。若要复活层1，须 `--base` 指到 S1v2 交付点重立白名单——属新验收，不是修 bug |
| `phase5_zones.txt` / `phase8_matrix.txt` | 阶段5/8 的人口与机制数 | 见 §四 | 退役 |

> **为什么单列这一类**：它比"退役"更危险——脚本能跑、会输出、还会打印 PASS/FAIL，
> 于是"判红"会被当成**新伤**、"没人跑"会被当成**没问题**。`memsys/docs/技术文档` 里
> 「层1 等价196/违例0 PASS」就是这么过期的（本批已改真）。

## 四 · 退役 43 件的硬编码断言陷阱（W2-N9）

退役件不止"跑不动"，还有**会把过时阈值当判据**的问题。实例（`tools/phase5_zones.txt`）：

```
:5   校验：人口基数 3871 且四区之和=人口，不平 exit 1。
:25  EXPECT = {"verified": 3093, "open": 702, "refuted": 52, "contradicted": 24}
:27  ok = len(P) == 3871 and all(by_status.get(k, 0) == v for k, v in EXPECT.items())
```

现值：`claim_ledger.csv` 记录 **11,281** 条、verified 7,023+ / open 3,037+（`99-MAP.md` 刷新节 2）。
⇒ 该件今天跑必然 `exit 1`，**但失败原因是阈值过期，不是账本不平**。同类：`phase8_matrix.txt:15` 断言 `==45`。
处置：**不改写退役件**（改写=伪造历史读数），在本件登记「阈值已过期」；如需复用逻辑，抄出后按现值重立判据。

## 五 · 发布面对账器（W4 批新增 · `publish_reconcile.py`）

| 项 | 内容 |
|---|---|
| 干什么 | 把 DR-8（一个扫描器的 canonical + 4 镜像）与 DR-9（一个 skill 的三份发布副本）的**一致性从叙述变成测量**：AST 去注释/docstring 后比代码面指纹；反引号引用的 `references/…`、`cases/…` 逐条查在不在 |
| 三态 | `FAIL` 只两型（断链 / 代码面差异）；`WARN(待裁)` 收版本落后、只在一方存在、字节层脱敏差；**宇宙为空 → exit 2**（装置没接上不判通过）；`WARN` 不计入通过 |
| 判据自检 | `--selftest` 四组：断链须被抓 / 补件须即闭 / 只差注释不报差异 / **改一条常数必报差异**（最后一组是正题：否则"代码零差异"是恒真） |
| 首跑读数 | 镜像 4 份代码面全同（`ast:2fba8b981bf3bb4c`）；断链 1（`skill/SKILL.md` 引 v3 而件缺）→ 加法式补齐后 `FAIL 0`、`rc=0`；待裁 18 项，逐条与处置见 `开工-20260923/03-发布面待裁清单-20260924.md` |
| 边界 | **不判"该不该同步"**，也不写任何发布副本；`_sekb-github-sync`/`_research-hub-sync` 两条只读线只出现在读数里，同步请求另行立案 |

## 六 · 门覆盖史（W2-N7 / N7b · 钩子变更声明）

| 洞 | 实况 | 处置 |
|---|---|---|
| **N7** R2 闸门只认 `.py$` | 仓内 **104** 个 Python 以 `.txt` 存在（tools 43 / red-team 60 / data 1，由 `exec(compile(...))` 载入）→ 往这些件里加恒真判据**不会被拦** | 选择器扩为 `\.(py\|txt)$` + 首行编码声明探测（实测 104/104 命中，纯文本台账不误纳） |
| **N7b** 路径读取被 git 转义 | `for f in $(git diff --cached --name-only …)`：非 ASCII 路径被转义成 `"\345\274\200…"` 字面量 ⇒ **中文名目录下的文件从未被扫描**（静默跳过）；含空格路径被词分裂 | 改 `-c core.quotepath=false` + `-z` NUL 分隔 + `while read -r -d ''`（进程替换，保 `exit 1` 生效） |

**钩子变更四处同步**（钩子自身头注第 3 行的规定）：
- 版本库副本 `tools/hooks/pre-commit` 与安装位 `.git/hooks/pre-commit` **已同步**（sha256 逐位相同）；
- sha256：`37030f796371c938…`（改前）→ **`2b73657426cddd229eacfbaec214ce4478a70a16a88cd434b736adeabc9e5752`**（改后，全值）；
- commit message 已声明；`INCREMENTAL-LOG.md` 已登记新 sha（W6 补账批）。

**四组探针实测**（改前/改后对照，探针已清理、工作树无残留）：

| 探针 | 新钩子 | 旧钩子 | 判读 |
|---|---|---|---|
| ASCII 路径 `.py`，含 `check(..., True)` | **rc=1 REJECT** | rc=1 REJECT | 基线未退化 |
| ASCII 路径 `.txt`（同内容） | **rc=1 REJECT** | rc=0 放行 | N7 盲区已补 |
| 中文名目录 `.py`（同内容） | **rc=1 REJECT** | rc=0 放行 | N7b 漏扫已补 |
| 纯文本 `.txt`（首行非编码声明） | rc=0 放行 | rc=0 放行 | 无误纳 |

## 七 · 本件不覆盖什么

1. 不登记 `build/` 下的装配器与测试（属产品线，见 `build/README.md`）；
2. 不登记 `imap/tools`、`imap2/tools`、`b-plan/tools`（各线自有工具，随其线冻结）；
3. 退役 42 件**未逐件核对其原始输出是否仍可复现**——只登记"输入已不存在"这一事实（`data/` 内有当时的产物快照）；
4. `.txt` 形态 Python 的**长期处置**（改回 `.py`？还是保留 `.txt` + 门扩面？）属治理位裁定，本件只做了门扩面这一半。

---
*审计区 · 2026-09-23 · W2 批（临时接手方）· 状态：待治理位验收*
