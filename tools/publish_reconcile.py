# -*- coding: utf-8 -*-
"""publish_reconcile.py — 发布面副本的机械对账器（开工批 W4 · 承载 DR-8 / DR-9 的"可机械判定"那一半）

为什么要有本件：DR-9 的现场是三份发布副本各自"看起来都正常"，逐字节对账才现形；
DR-8 的现场是一份自称"唯一权威"的扫描器另有四份镜像。两条的共同处置都写着
"确定权威副本 → 单向同步 → 哈希对账"，但**第二步（谁是权威、哪些件必须逐字一致）是裁决**，
不在执行区。本件因此只做两头：把差异**量出来并定性**，把不该静默的东西变成红门。

三面判据（互不混淆，"没查"与"查过没问题"不同形）：
  · **断链** FAIL —— 副本正文引用了 `references/<名>` 或 `cases/<名>`，而该副本目录里没有这个件；
  · **代码面差异** FAIL —— 同一文件各副本的**语法树**（去注释、去 docstring）不同；
  · **版本落后 / 逐字节不同但代码同 / 只在一方存在** 登记 ⚠ —— 需要裁决，本件不擅自判红也不判绿。

用法：
  py -X utf8 tools/publish_reconcile.py            # 对账（默认 --check）
  py -X utf8 tools/publish_reconcile.py --selftest # 判据自检：负向注入必须变红
退出码：0=无 FAIL 项（⚠ 仍会打印，⚠≠通过）；1=有 FAIL；2=宇宙为空（扫不到副本=装置没接上）
"""
import argparse
import ast
import hashlib
import os
import re
import sys
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 对账宇宙（冻结在此；改宇宙=改本表，须同批登记）────────────────────────
# DR-8：同一个扫描器的 canonical 与镜像。镜像允许**脱敏/出处行**不同，不允许代码不同。
SCANNER_COPIES = {
    "canonical": ["tools/invariant_scanner.py"],
    "mirror": ["skill/invariant_scanner.py",
               "sekb-plugin/skills/self-evolving-kb/invariant_scanner.py",
               "_sekb-github-sync/skills/self-evolving-kb/invariant_scanner.py",
               "_research-hub-sync/审计-自演化知识库治理/工件/tools/invariant_scanner.py"],
}
# DR-9：同一个 skill 的三份发布副本（整目录对账）。权威口径按 条目143=GitHub 那份；
# 本件只读不写，同步方向与"哪些件必须逐字一致"待裁决（见仓内工单）。
SKILL_COPIES = {
    "github(权威口径)": "_sekb-github-sync/skills/self-evolving-kb",
    "skill(仓内)": "skill",
    "sekb-plugin(发布车)": "sekb-plugin/skills/self-evolving-kb",
}
REF_MENTION = re.compile(r"`((?:references|cases)/[^`\s]+?)(?:\.md)?`")
_CODE_CACHE = {}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def code_shape(path):
    """→ 该文件的**代码面**指纹：AST 去 docstring 后 dump。

    注释与 docstring 不入指纹 ⇒ 脱敏改出处行不算差异；改逻辑必算差异。
    解析不了（非 py / 语法错）时退回归一化字节，**不静默返回 None**——None 会让"没法比"
    与"比过且相同"同形。
    """
    if path in _CODE_CACHE:
        return _CODE_CACHE[path]
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    node.body = body[1:] or [ast.Pass()]
        out = "ast:" + hashlib.sha256(ast.dump(tree).encode()).hexdigest()[:16]
    except (SyntaxError, UnicodeDecodeError, OSError) as e:
        out = f"raw:{sha(path)}#unparsable:{type(e).__name__}"
    _CODE_CACHE[path] = out
    return out


def rel(p):
    return p.replace("\\", "/")


def _mention_targets(text):
    """正文里被反引号引用的 references/cases 目标（去掉尾部通配与斜杠）。"""
    return [m.group(1).rstrip("/.*") for m in REF_MENTION.finditer(text)]


def _norm(name):
    """件名归一：只留中英文、数字与版本点号。

    本仓惯例是正文写 `总法则账面v3`、落盘名是 `总法则账面-v3-20260920.md`——
    不归一就会把自洽的副本全判成断链（误报一多，真断链就没人信了）。
    """
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff.]", "", name)


def check_broken_links(root):
    """→ [(副本, 引用目标, 出处文件)]：引用了却不在本副本目录里（断链）。"""
    bad = []
    for dp, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if d not in {".git", "__pycache__"}]
        for f in fs:
            if not f.endswith(".md"):
                continue
            fp = os.path.join(dp, f)
            with open(fp, encoding="utf-8", errors="replace") as h:
                text = h.read()
            for tgt in sorted(set(_mention_targets(text))):
                parent, leaf = tgt.rsplit("/", 1)
                d = os.path.join(root, parent.replace("/", os.sep))
                cand = os.path.join(root, tgt.replace("/", os.sep))
                if os.path.isfile(cand) or os.path.isdir(cand) or os.path.isfile(cand + ".md"):
                    continue
                if not os.path.isdir(d) or not any(_norm(x).startswith(_norm(leaf))
                                                   for x in os.listdir(d)):
                    bad.append((rel(os.path.basename(root)), tgt, rel(os.path.relpath(fp, root))))
    return bad


def reconcile_scanner(copies=None):
    """DR-8 → (fail, warn, 读数字)。fail=代码面不同；warn=字节不同而代码同（脱敏层差异）。"""
    copies = copies or SCANNER_COPIES
    canon = [c for c in copies["canonical"] if os.path.isfile(os.path.join(ROOT, c))]
    mir = [c for c in copies["mirror"] if os.path.isfile(os.path.join(ROOT, c))]
    if not canon or not mir:
        return [], [], {"universe": "empty"}
    ref = code_shape(os.path.join(ROOT, canon[0]))
    ref_sha = sha(os.path.join(ROOT, canon[0]))
    fails, warns, rows = [], [], [f"canonical {canon[0]} sha={ref_sha} 代码面={ref}"]
    for m in mir:
        p = os.path.join(ROOT, m)
        shape = code_shape(p)
        rows.append(f"镜像   {m} sha={sha(p)} 代码面={shape} "
                    + ("同" if shape == ref else "异"))
        if shape != ref:
            fails.append(("代码面差异", m, f"canonical={ref} 本件={shape}"))
        elif sha(p) != ref_sha:
            warns.append(("脱敏层差异（代码面已证相同）", m,
                          "差异必在注释/docstring；**禁止反向同步**（会把内部出处带回发布副本）"))
    return fails, warns, {"rows": rows, "n_mirror": len(mir)}


def reconcile_skills(copies=None):
    """DR-9 → (fail, warn, 读数字)。fail=断链；warn=与权威口径逐字节不同或只在一方存在。"""
    copies = copies or SKILL_COPIES
    have = {k: os.path.join(ROOT, v) for k, v in copies.items() if os.path.isdir(os.path.join(ROOT, v))}
    if not have:
        return [], [], {"universe": "empty"}
    fails, warns, rows = [], [], []
    for k, d in sorted(have.items()):
        links = check_broken_links(d)
        n_md = sum(1 for dp, _ds, fs in os.walk(d) for f in fs if f.endswith(".md"))
        rows.append(f"{k:18s} 目录={copies[k]} md件={n_md} 断链={len(links)}")
        for _c, tgt, src in links:
            fails.append(("断链", f"{copies[k]} :: {src}", f"引用 `{tgt}` 不在本副本内"))
    base = "github(权威口径)"
    if base in have:
        for k, d in have.items():
            if k == base:
                continue
            only_a, only_b, diff = _tree_vs(have[base], d)
            rows.append(f"{k:18s} vs 权威：仅权威有={len(only_a)} 仅本副本有={len(only_b)} "
                        f"同名异体={len(diff)}")
            for x in only_a:
                warns.append(("仅权威有", x, "本副本缺该件（是否该同步=待裁）"))
            for x in only_b:
                warns.append(("仅本副本有", x, "权威无此件（本地适配或历史残留=待裁）"))
            for x in diff:
                kind = "代码同/脱敏异" if code_shape(os.path.join(have[base], x)) == \
                    code_shape(os.path.join(d, x)) else "正文或代码异"
                warns.append(("同名异体", f"{base}/{x} vs {k}/{x}", kind))
    return fails, warns, {"rows": rows, "n_copies": len(have)}


def _tree_vs(a, b):
    """→ (仅 a 有, 仅 b 有, 同名且字节不同) 三组相对路径。"""
    fa, fb = _tree_files(a), _tree_files(b)
    return (sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa)),
            sorted(x for x in set(fa) & set(fb)
                   if sha(os.path.join(a, x)) != sha(os.path.join(b, x))))


def _tree_files(d):
    out = []
    for dp, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in {".git", "__pycache__"}]
        out += [rel(os.path.relpath(os.path.join(dp, f), d)) for f in fs]
    return out


# ── 判据自检：装置必须认得失败，否则"无 FAIL"就是恒真 ─────────────────────
def selftest():
    """造一个断链副本与一份改过逻辑的扫描器镜像，两项都必须被判 FAIL。"""
    td = tempfile.mkdtemp(prefix="pubcheck_")
    try:
        kb = os.path.join(td, "skill")
        os.makedirs(os.path.join(kb, "references"))
        with open(os.path.join(kb, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("见 `references/总法则账面v9`。\n")
        bad = check_broken_links(kb)
        assert len(bad) == 1 and bad[0][1] == "references/总法则账面v9", f"断链没被抓：{bad}"
        with open(os.path.join(kb, "references", "总法则账面-v9-20260101.md"),
                  "w", encoding="utf-8") as f:
            f.write("# 补上即闭合\n")
        assert check_broken_links(kb) == [], "补件后仍报断链（判据不认修复）"
        # 代码面判据两头都要判到：只差注释/docstring **不算**差异；改一条常数**必须**算。
        def w(name, text):
            p = os.path.join(td, name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p
        h_base = code_shape(w("base.py", "x = 1\n"))
        h_sani = code_shape(w("sanitized.py", '# 出处行已脱敏\n"""换了出处的 docstring"""\nx = 1\n'))
        h_mutt = code_shape(w("mutated.py", "x = 2\n"))
        assert h_base.startswith("ast:") and h_sani.startswith("ast:"), f"没走 AST 归一：{h_base}"
        assert h_base == h_sani, f"只差注释/docstring 却判代码不同（脱敏层放不过=误报）"
        assert h_base != h_mutt, "改了常数却判代码面相同 ⇒ 指纹不判别（这才是本自检的正题）"
        print("selftest: PASS（断链抓取＋修复即闭＋脱敏层放行＋改逻辑必红）")
        return 0
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="发布面副本对账（DR-8/DR-9 的机械那一半）")
    ap.add_argument("--check", action="store_true", help="默认动作：对账并打印")
    ap.add_argument("--selftest", action="store_true", help="判据自检（负向注入须变红）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    f1, w1, r1 = reconcile_scanner()
    f2, w2, r2 = reconcile_skills()
    if r1.get("universe") == "empty" or r2.get("universe") == "empty":
        print("universe empty：一个副本都没扫到 ⇒ 装置未接上，不判通过")
        return 2
    print("DR-8 扫描器副本（canonical vs 镜像）")
    for row in r1["rows"]:
        print(f"  {row}")
    print(f"DR-9 skill 三副本（{r2.get('n_copies')} 份在位）")
    for row in r2["rows"]:
        print(f"  {row}")
    for label, items in (("FAIL", f1 + f2), ("WARN(待裁)", w1 + w2)):
        print(f"\n{label} {len(items)} 项")
        for kind, where, why in items:
            print(f"  [{kind}] {where} —— {why}")
    print(f"\n读数：镜像 {r1['n_mirror']} 份 · 副本 {r2['n_copies']} 份 · "
          f"FAIL {len(f1) + len(f2)} · 待裁 {len(w1) + len(w2)}")
    print("口径：WARN≠通过，FAIL≠坏消息的全部——本件不判「该不该同步」，那只把不一致量出来。")
    return 1 if (f1 or f2) else 0


if __name__ == "__main__":
    sys.exit(main())
