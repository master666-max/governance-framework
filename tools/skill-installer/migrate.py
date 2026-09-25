# -*- coding: utf-8 -*-
"""migrate.py — 存量知识文件迁移工具（skill-installer v1 组件，20260919）
用途：把已有知识文件（.md/.txt）批量登记进账本体系的第一步——生成存量清单
（manifest）+ 每文件的 sha256 基准锚，供后续增量制图管线（双盲提取）消费。
用法：py -X utf8 migrate.py <知识目录> [输出manifest路径]
纪律：只读扫描，不修改任何源文件；输出=CSV 清单（file/sha256工作树态/bytes/lines）。
"""
import csv, hashlib, io, os, sys

def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    root = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "存量清单-manifest.csv")
    if not os.path.isdir(root):
        print(f"目录不存在: {root}"); sys.exit(1)
    rows = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not fn.lower().endswith((".md", ".txt")):
                continue
            p = os.path.join(dp, fn)
            try:
                raw = open(p, "rb").read()
                n = len(raw.decode("utf-8", "replace").splitlines())
            except OSError:
                continue
            rows.append([os.path.relpath(p, root).replace(os.sep, "/"),
                         sha256_file(p), len(raw), n])
    rows.sort()
    with io.open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256_wt", "bytes", "lines"])
        w.writerows(rows)
    print(f"存量清单: {len(rows)} 件 → {out}")
    print("下一步: ①sha256_wt 即每文件的基准锚（引用须标工作树态）；")
    print("        ②按增量制图管线做首轮双盲提取（说明书 v2 §第三章 3.7）；")
    print("        ③提取结果按账本九列 schema 追加进 claim_ledger.csv（R7 幂等）。")

if __name__ == "__main__":
    main()
