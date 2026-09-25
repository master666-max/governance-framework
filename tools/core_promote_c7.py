# core_promote_c7.py — CORE 扩核执行：passA(214 盲提) × 七圈账本行 交集提升（用户批准 2026-09-18）
# 口径照宪章 v3：±3 行 ∧ 包含度(短串被长串包含比例)≥60% ∧ 贪心一线一配
# Tier-1 CORE = 匹配 ∧ type/status 双一致；匹配但判定分歧 = CONTESTED
import csv, json, os, difflib, collections

AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
SB = os.path.join(AUD, "imap2", "sandbox", "nest")
DOCS_PREFIX = "大审查/"

led = list(csv.DictReader(open(os.path.join(AUD, "claim_ledger.csv"), encoding="utf-8-sig")))
# 重放钉死（02-bugs R2 家族二）：本脚本是当时账本的一次性预演，禁止随账本增长静默漂移。
BASE = 10745          # 作者时点账本行数-536（冻结于 20260924 修复）
if len(led) < BASE: raise SystemExit(f"账本({len(led)})短于固化基线10745——数据异常，拒绝重放")
if len(led) > BASE + 536: print(f"⚠ 账本已增至{len(led)}行：重放窗口钉死在作者时点(+536)，其后的行不在本预演内")
new = led[BASE:]

passA = []
for b in ("core6-passA",):
    for raw in open(os.path.join(AUD, "imap2", "data", "extract", b + ".jsonl"), encoding="utf-8"):
        if raw.strip():
            passA.append(json.loads(raw))

cache = {}
def line_of(p, ln):
    if p not in cache:
        cache[p] = open(os.path.join(SB, p.replace("/", os.sep)), encoding="utf-8", errors="replace").read().splitlines()
    return cache[p][ln - 1] if ln <= len(cache[p]) else None

def containment(a, b):
    x, y = (a, b) if len(a) <= len(b) else (b, a)
    sm = difflib.SequenceMatcher(None, x, y)
    return sum(bl.size for bl in sm.get_matching_blocks()) / max(len(x), 1)

# 锚点自验
af = sum(1 for q in passA if q["start_anchor"] not in line_of(q["file"], q["line"]) or q["end_anchor"] not in line_of(q["file"], q["line"]))

pairs = []
for j, q in enumerate(passA):
    for i, c in enumerate(new):
        if c["source_file"] != DOCS_PREFIX + q["file"]:
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
    ui.add(i); uj.add(j)
    matched.append((inc, i, j))

core, contested = [], []
for inc, i, j in matched:
    c, q = new[i], passA[j]
    row = dict(claim_id=c["claim_id"], source_file=c["source_file"],
               line=c["location_anchor"].rsplit(":", 1)[1],
               ledger_type=c["claim_type"], ledger_status=c["status"],
               passA_type=q["claim_type"], passA_status=q["status"],
               inclusion=round(inc, 3),
               tier="CORE" if (c["claim_type"] == q["claim_type"] and c["status"] == q["status"]) else "CONTESTED")
    (core if row["tier"] == "CORE" else contested).append(row)

out = os.path.join(AUD, "imap2", "data", "CORE-LEDGER-C7-M1M2.csv")
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["claim_id", "source_file", "line", "ledger_type",
                                      "ledger_status", "passA_type", "passA_status",
                                      "inclusion", "tier"])
    w.writeheader()
    for r in core + contested:
        w.writerow(r)

print(f"passA={len(passA)}  七圈账本行={len(new)}  锚点自验失败={af}")
print(f"匹配={len(matched)}  → Tier-1 CORE={len(core)}  CONTESTED={len(contested)}")
print("CORE type:", dict(collections.Counter(r["ledger_type"] for r in core)))
print("CORE status:", dict(collections.Counter(r["ledger_status"] for r in core)))
per = collections.Counter(r["source_file"].split("/")[-1][:22] for r in core)
for k, v in per.most_common():
    print(f"  {v:3d}  {k}")
print("落盘:", out)
