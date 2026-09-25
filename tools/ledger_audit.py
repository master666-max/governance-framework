# -*- coding: utf-8 -*-
"""ledger_audit.py — claim_ledger 全量机械审查（条目162，只读）
检查：①九列合规 ②claim_id 全量重复/跨代碰撞 ③superseded_by 链完整性
④锚点抽样回验（源文件三态：仍有效/悬空/文件缺失）⑤分布统计。
用法: py -X utf8 tools/ledger_audit.py [--sample 200] [--seed 20260921]
"""
import csv, hashlib, os, random, sys, collections
AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
LEDGER = os.path.join(AUD, "claim_ledger.csv")
# W2-N8（20260923 开工批）：锚点回验的搜索根。原第二项写死已废盘符（主区路径），现改为
# 环境变量 `AUDIT_MAIN` 显式传入；未传时该根**缺席且如实报出**——否则「主区没挂载」会被
# 误读成「引文腐烂」（计入 FILE-MISS），正是"什么都没查"与"查了没问题"同形的陷阱。
MAIN = os.environ.get("AUDIT_MAIN", "")
ROOTS = tuple(r for r in (AUD, MAIN,
                          os.path.join(AUD, "imap2", "sandbox", "nest"),
                          os.path.join(AUD, "imap2", "sandbox", "main")) if r)
sample_n, seed = 200, 20260921
if "--sample" in sys.argv: sample_n = int(sys.argv[sys.argv.index("--sample")+1])
if "--seed" in sys.argv: seed = int(sys.argv[sys.argv.index("--seed")+1])

raw = open(LEDGER, "rb").read()
sha = hashlib.sha256(raw).hexdigest()[:16]
text = raw.decode("utf-8-sig")
rows = list(csv.reader(text.splitlines()))
header, data = rows[0], rows[1:]
print(f"=== 0. 基线 ===")
print(f"行数 {len(data)}  sha256(LF归一)={hashlib.sha256(raw.replace(b'\\r\\n',b'\\n')).hexdigest()[:16]}")
if not MAIN:
    print("⚠ 主区根未提供（`AUDIT_MAIN=<路径>` 可纳入回验）——指向主区的锚会计入 FILE-MISS，"
          "**属覆盖面缺口，不是引文腐烂**")
_absent = [r for r in ROOTS if not os.path.isdir(r)]
if _absent:
    print(f"⚠ 搜索根缺席 {len(_absent)} 个：{_absent}")

print(f"\n=== 1. 列数合规 ===")
badcols = [i+2 for i, r in enumerate(data) if len(r) != 9]
print(f"非九列行：{len(badcols)}" + (f" 样例 {badcols[:5]}" if badcols else " ✓"))

print(f"\n=== 2. claim_id 唯一性（全量） ===")
ids = [r[0] for r in data if len(r) >= 1]
cnt = collections.Counter(ids)
dups = {k: v for k, v in cnt.items() if v > 1}
print(f"唯一 id {len(cnt)} / 总行 {len(ids)}；重复 id 组 {len(dups)}")
for k, v in list(dups.items())[:5]: print(f"   {k[:16]}… x{v}")
nonempty_ids = [i for i in ids if i.strip()]
print(f"空 id 行：{sum(1 for i in ids if not i.strip())}")

print(f"\n=== 3. superseded_by 链完整性 ===")
id_set = set(nonempty_ids)
sup_refs, broken = 0, []
for r in data:
    if len(r) == 9 and r[8].strip():
        sup_refs += 1
        if r[8].strip() not in id_set: broken.append(r[8].strip()[:16])
print(f"带 superseded_by 的行 {sup_refs}；指向不存在的 id {len(broken)}" + (f" 样例 {broken[:5]}" if broken else " ✓"))

print(f"\n=== 4. 分布统计 ===")
st = collections.Counter(r[7] for r in data if len(r) == 9)
ct = collections.Counter(r[3] for r in data if len(r) == 9)
stt = collections.Counter(r[6] for r in data if len(r) == 9)
def pref(eid):
    e = eid.strip()
    for p in ("AUDIT-LOG", "AUDIT2-", "AUDIT-", "SIM-", "REAL-", "DB-", "WEB-", "CBB-"):
        if e.startswith(p): return p
    return (e.split("-")[0] + "-") if "-" in e else "(空/其他)"
pf = collections.Counter(pref(r[5]) for r in data if len(r) == 9)
print("status:", dict(st)); print("claim_type:", dict(ct)); print("source_type:", dict(stt))
print("experiment_id 前缀（前12）:", dict(pf.most_common(12)))

print(f"\n=== 5. 锚点抽样回验（n={sample_n}, seed={seed}） ===")
random.seed(seed)
sam = random.sample(range(len(data)), min(sample_n, len(data)))
ok = stale = missing = other = 0
samples_bad = []
for idx in sam:
    r = data[idx]
    if len(r) != 9: continue
    f, anchor, q = r[1], r[2], r[4]
    # 解析 file@commit:line 或 <URL>@fetched 或 锚形态
    if "@" in anchor and ":" in anchor.split("@")[-1]:
        fc, ln = anchor.rsplit(":", 1)
        fp = fc.split("@")[0]
    else:
        other += 1; continue
    # 定位文件：审计区根 / 主区根 / 沙盒 / URL(跳过)
    cand = None
    if fp.startswith("http"): other += 1; continue
    for root in ROOTS:
        p = os.path.join(root, fp.replace("/", os.sep))
        if os.path.exists(p): cand = p; break
    if not cand:
        missing += 1; samples_bad.append(("FILE-MISS", fp[:60], ln)); continue
    try:
        lines = open(cand, encoding="utf-8", errors="replace").readlines()
        ln_i = int(ln)
        if ln_i < 1 or ln_i > len(lines): stale += 1; samples_bad.append(("LINE-OOR", fp[:60], ln)); continue
        if all(seg.strip() in lines[ln_i-1] for seg in q.split("...")):
            ok += 1
        else:
            stale += 1; samples_bad.append(("QUOTE-MISS", fp[:60], ln))
    except Exception as e:
        other += 1
tot = ok + stale + missing + other
print(f"可验 {tot}：锚仍有效 {ok} / 锚悬空(行内引文不再逐字命中) {stale} / 源文件缺失 {missing} / 其他形态 {other}")
for b in samples_bad[:10]: print("   ", b)
