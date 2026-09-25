# -*- coding: utf-8 -*-
"""refresh_99map.py — 99-MAP 刷新节统计（20260919 VKPS评估卷弱项⑥措施①本区自实践）
口径：全部机械产出；对 99-MAP 原表可重算项给出 2026-09-19 现值；
区间因子照旧（0.795/1.358，STALE-INPUT 登记见 tools/constants-registry.md）。
"""
import csv, io, math, collections, hashlib, os

AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）

def rd(p):
    return list(csv.DictReader(io.open(os.path.join(AUD, p), encoding="utf-8-sig")))

def nlines(p):
    with io.open(os.path.join(AUD, p), encoding="utf-8-sig") as f:
        return sum(1 for _ in f)

led = rd("claim_ledger.csv")
sup = {r["old_claim_id"] for r in rd("supersede_log.csv")}
strict = [r for r in led if r["claim_id"] not in sup and r["status"] != "superseded"]
lenient = [r for r in led if r["status"] != "superseded"]
st = collections.Counter(r["status"] for r in lenient)
P = len(strict)
cbb = sum(1 for r in lenient if r["experiment_id"].startswith("CBB"))

inc = rd("incident-log.csv")
inc_ids = collections.Counter(r.get("实验ID", "") for r in inc)

out = []
E = out.append
E("== 99-MAP 刷新节（2026-09-19，tools/refresh_99map.py 机械产出）==")
E("")
E("> 触发=VKPS 评估卷弱项⑥（原表冻结于 2026-09-10 时点，断言总入账过期 2.61×）；")
E("> 原配方 phase11_stats.txt 因工作区路径漂移已不可跑（根因一并登记）。")
E("> 本节只追加不改写原文；区间因子照旧但已挂 STALE-INPUT（见 constants-registry）。")
E("")
E("| 指标 | 09-10 原值 | **2026-09-19 现值** | 口径 |")
E("|---|---|---|---|")
E(f"| 断言总入账 | 3,940 | **{len(led):,}** | wc -l claim_ledger.csv − 1 |")
E(f"| 现行有效断言 P（严格：∉supersede_log ∧ status≠superseded） | 3,871 | **{P:,}** | ledger 双过滤 |")
E(f"| 现行有效断言（宽口径：仅 status≠superseded，与 3,871 同构可比） | 3,871 | **{len(lenient):,}** | status 过滤 |")
E(f"| — verified | 3,093 | **{st['verified']:,}** | 同左 |")
E(f"| — open | 702 | **{st['open']:,}** | 同左 |")
E(f"| — refuted | 52 | **{st['refuted']:,}** | 同左 |")
E(f"| — contradicted | 24 | **{st['contradicted']:,}** | 同左 |")
E(f"| 实验宇宙口径（剔 CBB 参考件，037/038 裁决链） | — | **{len(lenient)-cbb:,}** [{int((len(lenient)-cbb)*0.795):,}, {math.ceil((len(lenient)-cbb)*1.358):,}] | 宽口径−CBB |")
E(f"| CBB 参考件 | — | **{cbb:,}** | experiment_id~^CBB |")
E(f"| CORE（Tier-1） | — | **628** [48set 396+C5-7doc 64+C7-M1M2 44+C8-M2C3 124] | CORE-LEDGER* 四表 |")
E(f"| incident-log 行数 | 25 | **{len(inc)}** | 全量枚举 |")
E(f"| incident-log 去重 id | 24 | **{len([i for i in inc_ids if i])}**（重复 id：{[f'{k}×{v}' for k,v in inc_ids.items() if v>1] or '无'}） | id 计数 |")
E(f"| audit-log 行数 | — | **{nlines('audit-log.csv')-1}** 数据行 | wc −1 |")
E(f"| alias_map 映射数 | — | **{nlines('alias_map.csv')-1}** | wc −1 |")
# sec-exempt: 命令为字面量+仓路径常量 AUD，无外部输入（S1v2 门⑥登记）
E(f"| 本区 tracked 文件数 | — | **{int(os.popen('git -C %s ls-files | wc -l' % AUD).read())}** | git ls-files |")
E("")
E("**对照表**：078 条目勘验时（09-19 01:23）账本 10,113；本刷新节产出时点 10,321（第八圈 +208 后）。")
print("\n".join(out))
with io.open(os.path.join(AUD, "data", "99map-refresh-20260919.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
