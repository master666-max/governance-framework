# -*- coding: utf-8 -*-
"""S1_verify_src.py — 层1 机械验收：evocore 平移件 vs 源件逐行比对（白名单判定）

判据（S1 设计件 §3/§4）：
  W1 替换行：`from tunables import DEFAULTS` → `from .tunables import DEFAULTS`（恰 3 处）
  W2 追加行：docstring 溯源注记 `（evocore 平移版 · S1 · 源 memsys/... @ <commit>）`（仅追加）
  其余：等价行；**任何其他差异=违例**（违例≠0 即退出码 1）。

基准：git rev `--base`（默认 b19c9a4 = 平移前 HEAD）。旧路径映射见 _MAP。
用法: py -X utf8 tools/S1_verify_src.py [--base <rev>] [--repo <路径>]
"""
import argparse
import difflib
import os
import re
import subprocess
import sys

_MAP = {
    "evocore/tunables.py": "memsys/tunables.py",
    "evocore/retrieval.py": "memsys/engine/retrieval.py",
    "evocore/lifecycle.py": "memsys/engine/lifecycle.py",
    "evocore/decision.py": "memsys/engine/decision.py",
}
_W1_OLD = "from tunables import DEFAULTS"
_W1_NEW = "from .tunables import DEFAULTS"
_W2 = re.compile(r"^（evocore 平移版 · S1 · 源 (memsys/engine/[a-z]+\.py|memsys/tunables\.py) @ [0-9a-f]{7,40}）$")


def _git_show(repo, rev, path):
    out = subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit(f"git show 失败：{rev}:{path}\n{out.stderr}")
    return out.stdout


def _lines(text):
    ls = text.split("\n")
    if ls and ls[-1] == "":
        ls.pop()                     # 尾换行不算一行
    crlf = sum(1 for x in ls if x.endswith("\r"))
    return [x.rstrip("\r") for x in ls], crlf


def verify_file(repo, rev, new_rel, old_rel, expect_old):
    old_txt = _git_show(repo, rev, old_rel)
    new_path = os.path.join(repo, new_rel.replace("/", os.sep))
    with open(new_path, encoding="utf-8", newline="") as f:
        new_txt = f.read()
    old, old_crlf = _lines(old_txt)
    new, new_crlf = _lines(new_txt)
    eq = w1n = w2n = 0
    viol = []
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            eq += (i2 - i1)
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                o = old[i1 + k] if i1 + k < i2 else None
                n = new[j1 + k] if j1 + k < j2 else None
                if o == _W1_OLD and n == _W1_NEW:
                    w1n += 1
                else:
                    viol.append(f"L{j1+k+1} 非白名单替换: {o!r} -> {n!r}")
        elif tag == "insert":
            for k in range(j1, j2):
                m = _W2.match(new[k])
                if m and m.group(1) == expect_old:
                    w2n += 1
                else:
                    viol.append(f"L{k+1} 非白名单插入: {new[k]!r}")
        elif tag == "delete":
            for k in range(i1, i2):
                viol.append(f"旧行被删除(L{k+1}): {old[k]!r}")
    note = ""
    if old_crlf or new_crlf:
        note = f" [CRLF old={old_crlf} new={new_crlf}]"
    return eq, w1n, w2n, viol, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="b19c9a4")
    ap.add_argument("--repo", default=os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
    a = ap.parse_args()
    total_viol = 0
    t_w1 = t_w2 = 0
    for new_rel, old_rel in _MAP.items():
        eq, w1n, w2n, viol, note = verify_file(a.repo, a.base, new_rel, old_rel, old_rel)
        total_viol += len(viol)
        t_w1 += w1n
        t_w2 += w2n
        print(f"{new_rel:24s} 等价行 {eq:4d} / 白名单行 {w1n + w2n} (W1={w1n} W2={w2n}) / 违例 {len(viol)}{note}")
        for v in viol:
            print(f"    ✗ {v}")
    # 计数断言：W1 恰 3、W2 恰 4（设计件 §3 可数约束）
    ok_counts = (t_w1 == 3 and t_w2 == 4)
    print(f"\n违例合计：{total_viol}；W1 合计={t_w1}（应=3） W2 合计={t_w2}（应=4）")
    verdict = (total_viol == 0 and ok_counts)
    print("层1 判定：" + ("PASS" if verdict else "FAIL"))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
