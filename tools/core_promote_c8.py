# -*- coding: utf-8 -*-
"""core_promote_c8.py — 第八圈扩核预演：passA(两盲批 234) × 八圈账本新增 208 行 交集
口径照宪章 v3：±3 行 ∧ 包含度(短串被长串包含比例)≥60% ∧ 贪心一线一配
Tier-1 CORE 候选 = 匹配 ∧ type/status 双一致；匹配但判定分歧 = CONTESTED
预演产出=候选表，落档须用户批准（照 C5-7doc/C7-M1M2 先例）。
"""
import csv, json, os, difflib, collections

AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
SB = {"nest": os.path.join(AUD, "imap2", "sandbox", "nest"),
      "main": os.path.join(AUD, "imap2", "sandbox", "main")}
NEST_PREFIX = "大审查/"

led = list(csv.DictReader(open(os.path.join(AUD, "claim_ledger.csv"), encoding="utf-8-sig")))
# 重放钉死（02-bugs R2 家族二）：本脚本是当时账本的一次性预演，禁止随账本增长静默漂移。
BASE = 11073          # 作者时点账本行数-208（冻结于 20260924 修复）
if len(led) < BASE: raise SystemExit(f"账本({len(led)})短于固化基线11073——数据异常，拒绝重放")
if len(led) > BASE + 208: print(f"⚠ 账本已增至{len(led)}行：重放窗口钉死在作者时点(+208)，其后的行不在本预演内")
new = led[BASE:]

passA = []
for b in ("core8-passA-a", "core8-passA-b"):
    for raw in open(os.path.join(AUD, "imap2", "data", "extract", b + ".jsonl"), encoding="utf-8"):
        if raw.strip():
            r = json.loads(raw); r["_batch"] = b; passA.append(r)

def roots_of(f):
    return "nest" if os.path.exists(os.path.join(SB["nest"], f.replace("/", os.sep))) else "main"

cache = {}
def line_of(f, ln):
    if f not in cache:
        repo = roots_of(f)
        cache[f] = open(os.path.join(SB[repo], f.replace("/", os.sep)), encoding="utf-8", errors="replace").read().splitlines()
    return cache[f][ln - 1] if ln <= len(cache[f]) else None

def containment(a, b):
    x, y = (a, b) if len(a) <= len(b) else (b, a)
    sm = difflib.SequenceMatcher(None, x, y)
    return sum(bl.size for bl in sm.get_matching_blocks()) / max(len(x), 1)

# 锚点自验（passA 侧逐字双验证）
af = 0
for q in passA:
    ln = line_of(q["file"], q["line"])
    if ln is None or q["start_anchor"] not in ln or q["end_anchor"] not in ln:
        af += 1
print(f"passA 锚点自验: {len(passA)-af}/{len(passA)} pass")

pairs = []
for j, q in enumerate(passA):
    canon = (NEST_PREFIX + q["file"]) if roots_of(q["file"]) == "nest" else q["file"]
    for i, c in enumerate(new):
        if c["source_file"] != canon:
            continue
        cln = int(c["location_anchor"].rsplit(":", 1)[1])
        if abs(cln - q["line"]) <= 3:
            inc = containment(c["verbatim_quote"], q["start_anchor"] + "…" + q["end_anchor"])
            if inc >= 0.60:
                pairs.append((inc, i, j))
pairs.sort(reverse=True)
ui, uj, matched = set(), set(), []
for inc, i, j in pairs:
    if i in ui or j in uj:
        continue
    ui.add(i); uj.add(j); matched.append((inc, i, j))

core, contested = [], []
for inc, i, j in matched:
    c, q = new[i], passA[j]
    row = dict(claim_id=c["claim_id"], source_file=c["source_file"],
               line=c["location_anchor"].rsplit(":", 1)[1],
               ledger_type=c["claim_type"], ledger_status=c["status"],
               passA_batch=q["_batch"], passA_type=q["claim_type"], passA_status=q["status"],
               inclusion=round(inc, 3),
               tier="CORE" if (c["claim_type"] == q["claim_type"] and c["status"] == q["status"]) else "CONTESTED")
    (core if row["tier"] == "CORE" else contested).append(row)

out = os.path.join(AUD, "imap2", "data", "CORE-LEDGER-C8-预演.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(core[0].keys()) if core else
                       ["claim_id","source_file","line","ledger_type","ledger_status","passA_batch","passA_type","passA_status","inclusion","tier"])
    w.writeheader()
    for r in core + contested:
        w.writerow(r)

byf = collections.Counter(r["source_file"].split("/")[-1][:24] for r in core + contested)
print(f"匹配 {len(matched)}（账本未配 {208-len(matched)} / passA 未配 {len(passA)-len(matched)}）")
print(f"Tier-1 CORE 候选 {len(core)} / CONTESTED 候选 {len(contested)}")
print("覆盖文件:")
for k, v in byf.most_common():
    print(f"  {v:3d}  {k}")
print(f"候选表 → {out}")
