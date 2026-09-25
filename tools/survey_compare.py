# -*- coding: utf-8 -*-
"""survey_compare.py — B3 跨位置比对（条目155，只读）
读 B1 枚举 CSV：①同件分组（件名归一：剥 skills/self-evolving-kb/ 与发布车前缀）
②组内逐位置 sha256(LF归一) 判 ≡/异 ③位置对差集。
用法: py -X utf8 tools/survey_compare.py
"""
import os, csv, collections, re
AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
CSVIN = os.path.join(AUD, "survey-20260921", "说明书家族-枚举-20260921.csv")

def canon(rel):
    r = rel
    for pre in ("skills/self-evolving-kb/", "skills/"):
        if r.startswith(pre): r = r[len(pre):]
    return r

rows = list(csv.DictReader(open(CSVIN, encoding="utf-8-sig")))
groups = collections.defaultdict(dict)  # canon_name -> {pos: (sha, bytes, rel)}
for r in rows:
    if r["position"].startswith("5-") or r["position"].startswith("1b-"):
        continue  # 主区/根级单件另行处理
    groups[canon(r["relpath"])][r["position"]] = (r["sha256_lf16"], r["bytes"])

print("=== A. 多位置同件比对（仅列出现在 ≥2 位置的件） ===")
multi = 0; incons = 0
for name, pos in sorted(groups.items()):
    if len(pos) < 2: continue
    multi += 1
    shas = {p: v[0] for p, v in sorted(pos.items())}
    uniq = set(shas.values())
    mark = "≡ 全同" if len(uniq) == 1 else "✗ 不一致"
    if len(uniq) != 1: incons += 1
    print(f"[{mark}] {name}")
    for p, s in sorted(shas.items()): print(f"    {p}: {s}")
print(f"--- 多位置件 {multi} 组，其中不一致 {incons} 组 ---")

print()
print("=== B. 各位置独有件（相对其他位置的差集） ===")
all_pos = sorted({r["position"] for r in rows if not r["position"].startswith(("5-", "1b-"))})
for p in all_pos:
    mine = {canon(r["relpath"]) for r in rows if r["position"] == p}
    others = set()
    for q in all_pos:
        if q != p: others |= {canon(r["relpath"]) for r in rows if r["position"] == q}
    only = sorted(mine - others)
    print(f"[{p}] 独有 {len(only)} 件: {only if len(only) <= 12 else only[:12]}")
