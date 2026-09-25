# core_expand_c5.py — 第五圈扩核：7 文档二轮盲提 × 账本首轮 交集匹配（2026-09-16）
# 口径照宪章 v3：±3 行 ∧ 包含度≥60%（SequenceMatcher） ∧ 贪心一线一配
# Tier-1 CORE = 匹配 ∧ claim_type ∧ status 双一致；匹配但判定分歧 = Tier-2 CONTESTED
import csv, json, os, difflib, collections

AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
SB = os.path.join(AUD, "imap2", "sandbox", "nest")
DOCS = {
    "衔尾蛇/reports/E1-R_再应用结果报告-20260916.md",
    "衔尾蛇/reports/E1-R_再验收预注册-20260916.md",
    "混元/两线联合-EJ3EJ4-20260911/报告-PB2-20260916.md",
    "混元/两线联合-EJ3EJ4-20260911/报告-PB2v2-20260916.md",
    "衔尾蛇/reports/P-A2_总法则第八验_结果报告-20260916.md",
    "衔尾蛇/reports/P-A2_总法则第八验_预注册执行书-20260916.md",
    "衔尾蛇/reports/P-A2_影子批次扩展_预注册-20260916.md",
}

# 首轮 = 账本中 7 文件的行（第五圈入账）
led = [r for r in csv.DictReader(open(os.path.join(AUD, "claim_ledger.csv"), encoding="utf-8-sig"))
       if r["source_file"] in {"大审查/" + d for d in DOCS}]
# 二轮盲提
r2 = []
for b in ("core5-a", "core5-b"):
    for raw in open(os.path.join(AUD, "imap2", "data", "extract", b + ".jsonl"), encoding="utf-8"):
        if raw.strip():
            r2.append(json.loads(raw))

# 逐字复核二轮锚点（对沙盒文件）
cache = {}
def line_of(path, ln):
    if path not in cache:
        cache[path] = open(os.path.join(SB, path.replace("/", os.sep)),
                           encoding="utf-8", errors="replace").readlines()
    return cache[path][ln - 1].rstrip("\r\n")
anchor_fail = sum(1 for r in r2
                  if r["start_anchor"] not in line_of(r["file"], r["line"])
                  or r["end_anchor"] not in line_of(r["file"], r["line"]))

# 候选对（同文件 ∧ |行差|≤3）；包含度=短串被长串包含比例（v3 口径的正解）
def containment(s1, s2):
    a, b = (s1, s2) if len(s1) <= len(s2) else (s2, s1)
    sm = difflib.SequenceMatcher(None, a, b)
    return sum(bl.size for bl in sm.get_matching_blocks()) / max(len(a), 1)

pairs = []
for j, q in enumerate(r2):
    for i, a in enumerate(led):
        if a["source_file"] != "大审查/" + q["file"]:
            continue
        aln = int(a["location_anchor"].rsplit(":", 1)[1])
        if abs(aln - q["line"]) <= 3:
            inc = containment(a["verbatim_quote"],
                              q["start_anchor"] + "…" + q["end_anchor"])
            if inc >= 0.60:
                pairs.append((inc, i, j))
pairs.sort(reverse=True)
used_i, used_j, matched = set(), set(), []
for inc, i, j in pairs:
    if i in used_i or j in used_j:
        continue
    used_i.add(i); used_j.add(j)
    matched.append((i, j, inc))

core, contested = [], []
for i, j, sim in matched:
    a, q = led[i], r2[j]
    row = dict(claim_id=a["claim_id"], source_file=a["source_file"],
               line=a["location_anchor"].rsplit(":", 1)[1],
               ledger_type=a["claim_type"], ledger_status=a["status"],
               r2_type=q["claim_type"], r2_status=q["status"], inclusion=round(inc, 3))
    (core if (a["claim_type"] == q["claim_type"] and a["status"] == q["status"]) else contested).append(row)

out = os.path.join(AUD, "imap2", "data", "CORE-LEDGER-C5-EXPAND.csv")
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["claim_id", "source_file", "line", "ledger_type",
                                      "ledger_status", "r2_type", "r2_status", "inclusion", "tier"])
    w.writeheader()
    for r in core: r["tier"] = "CORE"; w.writerow(r)
    for r in contested: r["tier"] = "CONTESTED"; w.writerow(r)

print(f"首轮(账本7文件)={len(led)}  二轮盲提={len(r2)}  锚点复核失败={anchor_fail}")
print(f"匹配={len(matched)}  → Tier-1 CORE={len(core)}  Tier-2 CONTESTED={len(contested)}")
print(f"二轮未匹配(维持SAMPLE)={len(r2)-len(matched)}  首轮未匹配(账本侧)={len(led)-len(matched)}")
print("CORE 的 type 分布:", dict(collections.Counter(r["ledger_type"] for r in core)))
print("CORE 的 status 分布:", dict(collections.Counter(r["ledger_status"] for r in core)))
per = collections.Counter(r["source_file"].split("/")[-1][:24] for r in core)
print("CORE 按文件:", dict(per))
print("落盘:", out)
