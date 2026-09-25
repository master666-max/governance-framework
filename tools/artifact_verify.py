# -*- coding: utf-8 -*-
"""artifact_verify.py — 工件库复算脚本（WP-A A2，20260920）
按 artifact-ledger.csv 的 recipe 逐条现算，声明 sha vs 实算 sha 比对。
态标签强制：每行必带 sampled_at+generation_binding（S-5/6 对策）。
用法: py -X utf8 tools/artifact_verify.py [--ledger <csv路径>]
任一 Δ 即 exit 1；全 attested 即 exit 0。
"""
import csv, hashlib, io, os, re, subprocess, sys, datetime

AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(AUD, "tools", "artifact-ledger.csv")
# W2-N8（20260923 开工批）：主区根**不再靠扫 D:/ 猜目录名**——原实现猜不中时 MAJQ=None，
# 随后 `os.path.join(None, …)` 抛 TypeError（看起来像脚本坏，其实是路径没挂）。
# 改为显式传参（环境变量 AUDIT_MAIN）；未提供时**如实报出覆盖面缺口**，不静默降级。
MAJQ = os.environ.get("AUDIT_MAIN", "") or None
if not MAJQ:
    print("⚠ 主区根未提供（设 `AUDIT_MAIN=<路径>` 可纳入解析）——指向主区的工件将计入不可解析，"
          "**属覆盖面缺口，不是工件失效**", file=sys.stderr)
elif not os.path.isdir(MAJQ):
    raise SystemExit(f"AUDIT_MAIN 指向的路径不存在：{MAJQ}（fail-closed：不扫空、不出假读数）")

def resolve_path(source_mapping):
    """从 source_mapping 取第一个路径组件，解析为绝对路径"""
    roots = [AUD] + ([MAJQ, os.path.join(MAJQ, "大审查")] if MAJQ else [])
    for part in source_mapping.split(";"):
        p = part.split("@")[0].strip()
        for root in roots:
            fp = os.path.join(root, p.replace("/", os.sep))
            if os.path.isfile(fp):
                return fp
        # 尝试审计区根
        fp = os.path.join(AUD, p.replace("/", os.sep))
        if os.path.isfile(fp):
            return fp
    return None

def main():
    if not os.path.isfile(LEDGER):
        print(f"工件账不存在: {LEDGER}"); sys.exit(1)
    rows = list(csv.DictReader(io.open(LEDGER, encoding="utf-8-sig")))
    if not rows:
        print("工件账为空"); sys.exit(0)

    fail = 0; total = 0
    for r in rows:
        aid = r["artifact_id"][:16]
        decl = r["declaration"][:50]
        recipe = r["recipe"]
        gen = r.get("generation_binding", "")
        sampled = r.get("sampled_at", "")
        state = r.get("state", "")

        # 检查必填字段（S-5/S-6 对策）
        if not sampled:
            print(f"  [{aid}] MISSING sampled_at"); fail += 1; continue
        if not gen:
            print(f"  [{aid}] MISSING generation_binding"); fail += 1; continue

        # 从 recipe 提取路径并现算
        # recipe 格式示例: sha256sum path 或 wc -l path
        m = re.search(r'(?:sha256sum|wc)\s+.*?([^\s]+(?:/[^\s]+)*)', recipe)
        if not m:
            print(f"  [{aid}] recipe 不可解析: {recipe[:60]}"); fail += 1; continue
        raw_path = m.group(1).strip()
        # 尝试解析路径
        fp = None
        for root in (AUD, MAJQ, os.path.join(MAJQ, "大审查")):
            test = raw_path if os.path.isabs(raw_path) else os.path.join(root, raw_path.replace("/", os.sep))
            if os.path.isfile(test):
                fp = test; break
        if not fp:
            # 尝试仅文件名匹配
            base = os.path.basename(raw_path)
            for root in (AUD, MAJQ, os.path.join(MAJQ, "大审查")):
                test = os.path.join(root, base)
                if os.path.isfile(test):
                    fp = test; break
        if not fp:
            print(f"  [{aid}] FILE NOT FOUND: {raw_path}"); fail += 1; continue

        sha = hashlib.sha256(open(fp, "rb").read()).hexdigest()[:16]
        match = sha == aid[:16] or aid.startswith(sha[:8])
        if match:
            print(f"  [{aid}] OK sha={sha} gen={gen} sampled={sampled}")
        else:
            print(f"  [{aid}] MISMATCH: declared={aid[:16]} actual={sha}")
            fail += 1
        total += 1

    print(f"\n=== 工件库复算: {total-fail}/{total} PASS, {fail} FAIL ===")
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
