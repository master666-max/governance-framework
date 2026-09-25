# -*- coding: utf-8 -*-
"""survey_manuals.py — B1 说明书全家族机械枚举（条目155，只读）
六位置全量枚举 .md/.txt/.csv 文档件 + 逐件双基准 sha256（工作树态/LF归一态）。
用法: py -X utf8 tools/survey_manuals.py
产出: survey-20260921/说明书家族-枚举-20260921.csv
"""
import os, csv, hashlib
AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
MAIN = os.environ.get("AUDIT_MAIN", "")     # W2-N8：主区根不写死（原写死路径已废）；未提供则该位置如实记「<位置不存在>」，不冒充 0 件
DSH = os.environ.get("DSH_SKILL_DIR", "")   # W2-N8：DSH 部署位不写死（原值含本机用户名，属越界个人信息）
POSITIONS = [
    ("1-审计skill", os.path.join(AUD, "skill"), 6),
    ("1b-审计根说明书件", AUD, 1),  # maxdepth 1：根级说明书族单件
    ("2-GitHub权威", os.path.join(AUD, "_sekb-github-sync"), 6),
    ("3-发布车", os.path.join(AUD, "sekb-plugin"), 6),
    ("4-DSH包", os.path.join(AUD, "sekb-dsh-package"), 6),
    ("5-主区部署", MAIN, 1),        # 仅根级治理件
    ("6-DSH侧部署", DSH, 6),
]
EXTS = {".md", ".txt", ".csv"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".dsh-reef"}
ROOT_ONLY_HINT = ("说明书", "目录地址", "计划书", "M系列排期", "可行性分析", "下发单")  # 1b 与 5 的根级过滤提示

def sha16(raw, lf=False):
    b = raw.replace(b"\r\n", b"\n") if lf else raw
    return hashlib.sha256(b).hexdigest()[:16]

def emit(rows, pos, root, rel, full):
    ext = os.path.splitext(rel)[1].lower()
    if ext not in EXTS: return
    raw = open(full, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")[:60]
    rows.append([pos, rel, len(raw), sha16(raw), sha16(raw, True),
                 len(text.splitlines()), first])

def main():
    rows = []
    for pos, root, maxd in POSITIONS:
        if not os.path.isdir(root):
            rows.append([pos, "<位置不存在>", "", "", "", "", ""]); continue
        for dp, ds, fs in os.walk(root):
            ds[:] = [d for d in ds if d not in SKIP_DIRS]
            rel_dp = os.path.relpath(dp, root)
            depth = 0 if rel_dp == "." else rel_dp.count(os.sep) + 1
            if depth > maxd: ds[:] = []; continue
            for f in fs:
                full = os.path.join(dp, f)
                rel = f if rel_dp == "." else os.path.join(rel_dp, f)
                rel = rel.replace(os.sep, "/")
                if maxd == 1 and pos in ("1b-审计根说明书件", "5-主区部署"):
                    # 根级过滤：说明书族相关件才收（排除审计区大量工作件/数据件）
                    if not (any(h in f for h in ROOT_ONLY_HINT)
                            or f.startswith(("ANCHOR", "EXCL", "claim_ledger", "supersede",
                                             "预注册SOP", "audit-log", "incident-log",
                                             "HANDOVER", "续跑交接", "README"))):
                        continue
                emit(rows, pos, root, rel, full)
    out = os.path.join(AUD, "survey-20260921", "说明书家族-枚举-20260921.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["position", "relpath", "bytes", "sha256_raw16", "sha256_lf16", "lines", "first_line"])
        w.writerows(rows)
    import collections
    c = collections.Counter(r[0] for r in rows)
    print(f"枚举 {len(rows)} 件 → {out}")
    for k, v in c.items(): print(f"  {k}: {v}")

main()
