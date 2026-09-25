# -*- coding: utf-8 -*-
"""reuse_census.py — 复用/新增/删除/改写四数巡检（S1v2 · T7；总工单 G7/P20）

用途：给任一提交区间出"量增质降"读数——净增**全是新逻辑**还是**验证与门面**？
口径（全部 git 机械口径，可复跑；详见《S1设计v2》§1.5）：
  复用行 = 重命名/复制目标文件的行数（逐字节承袭的存量）        [R/C 状态]
  新增行 = 纯新增文件的行数（新交付件）                        [A 状态]
  删除行 = 全区间删除行数（numstat deleted 汇总）               [M/D 状态]
  改写行 = 重命名/复制文件内部的增删行（搬移期的小改动）        [R/C 状态]
  改动行 = 普通修改文件内部的增删行                            [M 状态]
  重写率 = 改写行 /（复用行 + 改写行）——"重写"的报警面
用法: py -X utf8 tools/reuse_census.py <A..B | 单rev | A..> [--repo .]
      （单 rev 视为 <rev>~1..<rev>；"A.." = A 到工作树；只读操作）
边界（如实声明）：**未跟踪（untracked）文件不计入**——工作树口径下新件先 `git add`
      再复算方可见（工具见此情形会提示）。
"""
import argparse
import os
import subprocess
import sys


def git(repo, *args):
    r = subprocess.run(["git", "-c", "core.quotepath=false", "-C", repo, *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{r.stderr.strip()}")
    return r.stdout


def tip_lines(repo, rev, path):
    if not rev:                                  # 工作树口径（未提交区间 "A.."）
        p = os.path.join(repo, path)
        if not os.path.isfile(p):
            return 0
        with open(p, encoding="utf-8", errors="replace") as f:
            return len(f.read().split("\n")) - 1
    out = subprocess.run(["git", "-c", "core.quotepath=false", "-C", repo, "show", f"{rev}:{path}"],
                         capture_output=True, text=True, encoding="utf-8")
    return len(out.stdout.split("\n")) - 1 if out.returncode == 0 else 0


def numstat_path(field: str) -> str:
    """numstat 的路径字段 → 新路径。兼容三种格式：
    'path' · 'old => new' · '{old => new}/tail'（花括号压缩）。"""
    if "=>" not in field:
        return field
    pre, brace, rest = field.partition("{")
    if not brace:
        return field.split("=>")[1].strip()
    inner, _, post = rest.partition("}")
    return (pre + inner.split("=>")[1].strip() + post).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("range")
    ap.add_argument("--repo", default=os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
    a = ap.parse_args()
    if a.range.endswith(".."):                   # "A.." = A 到**工作树**（未提交区间）
        rng, tip = a.range[:-2], ""              # 单 rev 形态：git diff <rev> 即对工作树
    else:
        rng = a.range if ".." in a.range else f"{a.range}~1..{a.range}"
        tip = rng.split("..")[1] or "HEAD"
    name_status = [ln.split("\t") for ln in git(a.repo, "diff", "-M", "-C", "--name-status", rng).splitlines() if ln.strip()]
    numstat = {}
    for ln in git(a.repo, "diff", "-M", "-C", "--numstat", rng).splitlines():
        if not ln.strip():
            continue
        add, dele, field = ln.split("\t", 2)
        numstat[numstat_path(field)] = (int(add) if add.isdigit() else 0, int(dele) if dele.isdigit() else 0)
    reused = new = rewritten = changed = deleted = 0
    rows = []
    for parts in name_status:
        st = parts[0]
        if st.startswith("R") or st.startswith("C"):
            old, newp = parts[1], parts[2]
            lines = tip_lines(a.repo, tip, newp)
            reused += lines
            ad = numstat.get(newp, (0, 0))
            rewritten += ad[0] + ad[1]
            rows.append((f"{st} {old} → {newp}", lines, ad))
        elif st == "A":
            lines = tip_lines(a.repo, tip, parts[1])
            new += lines
            rows.append((f"A {parts[1]}", lines, numstat.get(parts[1], (0, 0))))
        elif st == "D":
            ad = numstat.get(parts[1], (0, 0))
            deleted += ad[1]
            rows.append((f"D {parts[1]}", 0, ad))
        else:
            ad = numstat.get(parts[1], (0, 0))
            changed += ad[0] + ad[1]
            deleted += ad[1]
            rows.append((f"{st} {parts[1]}", 0, ad))
    print(f"区间 {rng}（tip={tip}）")
    print(f"{'条目':<52} | {'承运行':>6} | {'+':>5} | {'-':>5}")
    for name, carried, ad in rows:
        print(f"{name[:52]:<52} | {carried:>6} | {ad[0]:>5} | {ad[1]:>5}")
    base = reused + rewritten
    print(f"\n复用行 {reused} · 新增行 {new} · 删除行 {deleted} · 改写行 {rewritten} · 改动行 {changed}")
    print(f"重写率（改写/(复用+改写)）= {(rewritten / base):.4f}" if base else "重写率：无搬移面，不适用")
    if not tip and new == 0:
        print("提示：工作树口径不含未跟踪文件——新件先 `git add` 再复算。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
