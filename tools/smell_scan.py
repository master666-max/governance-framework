# -*- coding: utf-8 -*-
"""smell_scan.py — 坏味候选扫描器（S1v2 · T5①②；对齐 总工单 P19/G5）

分工声明（与既有仪器同款）：门（`code_quality_gate.py`）=**拒**；本件=**候选**输出
（与 `tools/invariant_scanner.py` 的"候选制"同款纪律——③ 级可否证，不直接拦提交）。
两项检测：
  ① 重复块（B1 型）：连续 2 行"实质行"逐字重复且窗口字符数 ≥ MIN_TOTAL
     （2 行=实战最小可辨重复；字符数下限挡 `return x` 级噪声）——同批文件内/跨文件均查；
  ② 魔法数：**AST 数字常量**（|值| ≥ 100）——不用正则（防 docstring/字符串误报）；
     同行 `# smell-exempt: 理由` 可逐行豁免。
基线豁免：`tools/smell-baseline.txt`，每行 `<kind> <path>:<line>`（# 后可写理由）；
  重复块组内**任一**位置被登记即整组豁免（有据的接受项，如"测试文件刻意独立可运行"）。
用法: py -X utf8 tools/smell_scan.py <path...> [--baseline tools/smell-baseline.txt] [--report]
      --report=纯报告（exit 0）；默认=有未登记候选则 exit 1（供巡检/钩子挂钩）。
"""
import argparse
import ast
import os
import re
import sys

WINDOW = 2
MIN_TOTAL = 60
MIN_VALUE = 100
_EXEMPT = re.compile(r"#\s*smell-exempt:\s*\S")
_SKIP_LINE = {"}", ")", "):", "],", "}", "else:", "try:", "finally:", "return", "break", "continue"}


def _substantive(line: str) -> bool:
    s = line.strip()
    if not s or s.startswith("#") or s.startswith(("import ", "from ")):
        return False
    if s in _SKIP_LINE:
        return False
    return len(s) >= 8


def _read_lines(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().split("\n")


def find_dup_blocks(paths):
    """窗口法：连续 WINDOW 行实质行逐字相同且窗口足够长（MIN_TOTAL）→ 候选组。"""
    windows = {}
    for p in paths:
        lines = _read_lines(p)
        for i in range(len(lines) - WINDOW + 1):
            chunk = [ln.rstrip() for ln in lines[i:i + WINDOW]]
            if not all(_substantive(c) for c in chunk):
                continue
            if sum(len(c.strip()) for c in chunk) < MIN_TOTAL:
                continue
            windows.setdefault("\n".join(chunk), []).append((p, i + 1))
    groups = [v for v in windows.values() if len(v) > 1]
    return sorted(groups, key=lambda g: (-len(g), g[0]))


def _named_constant_nodes(tree):
    """收集"具名赋值右侧的数字字面量"节点 id：把值赋给名字（x = 200 / x: int = 200 /
    A, B = 900, 80 元组解包）是魔法数的**解法**而非魔法数本身——这些节点不算候选。"""
    named = set()
    for n in ast.walk(tree):
        targets = []
        if isinstance(n, ast.Assign):
            targets = n.targets
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            targets = [n.target]
        flat = []
        for t in targets:
            flat.extend(t.elts if isinstance(t, ast.Tuple) else [t])
        if not flat or not all(isinstance(t, (ast.Name, ast.Attribute)) for t in flat):
            continue
        val = getattr(n, "value", None)
        if isinstance(val, ast.Constant):
            named.add(id(val))
        elif isinstance(val, ast.UnaryOp) and isinstance(val.operand, ast.Constant):
            named.add(id(val.operand))          # E_PARSE = -32700（负号：UnaryOp 包常量）
        elif isinstance(val, ast.Tuple):        # A, B = 900, 80（元组内全常量才算具名）
            for elt in val.elts:
                if isinstance(elt, ast.Constant):
                    named.add(id(elt))
                elif isinstance(elt, ast.UnaryOp) and isinstance(elt.operand, ast.Constant):
                    named.add(id(elt.operand))
    return named


def find_magic_numbers(paths):
    """AST 数字常量（|值| ≥ MIN_VALUE，排除具名赋值右侧）；返回 [(path, line, 值)]。"""
    out = []
    for p in paths:
        lines = _read_lines(p)
        try:
            tree = ast.parse("\n".join(lines))
        except SyntaxError:
            continue
        skip = _named_constant_nodes(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
                    and not isinstance(n.value, bool) and abs(n.value) >= MIN_VALUE \
                    and id(n) not in skip:
                ln = lines[n.lineno - 1] if n.lineno - 1 < len(lines) else ""
                if not _EXEMPT.search(ln):
                    out.append((p, n.lineno, n.value))
    return out


def load_baseline(path):
    """返回 {"dup": set(path:line), "magic": set(path:line)}。"""
    base = {"dup": set(), "magic": set()}
    if not (path and os.path.isfile(path)):
        return base
    for raw in _read_lines(path):
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        kind, _, loc = ln.partition(" ")
        loc = loc.split("#", 1)[0].strip()
        if kind in base and ":" in loc:
            base[kind].add(loc)
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--baseline", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "smell-baseline.txt"))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    base = load_baseline(a.baseline)
    dups = find_dup_blocks(a.paths)
    magics = find_magic_numbers(a.paths)
    live_dups = [g for g in dups
                 if not any(f"{p}:{ln}" in base["dup"] for p, ln in g)]
    live_magic = [(p, ln, v) for p, ln, v in magics if f"{p}:{ln}" not in base["magic"]]
    print(f"smell_scan：文件 {len(a.paths)} · 重复块候选 {len(dups)}（基线豁免 {len(dups)-len(live_dups)}）"
          f" · 魔法数候选 {len(magics)}（基线豁免 {len(magics)-len(live_magic)}）")
    for g in live_dups[:20]:
        print(f"  [DUP] {WINDOW} 行逐字重复 ×{len(g)}：")
        for p, ln in g:
            print(f"        {p}:{ln}")
    for p, ln, v in live_magic[:40]:
        print(f"  [MAGIC] {p}:{ln} = {v}")
    live = len(live_dups) + len(live_magic)
    print(f"未登记候选：{live}（重复块组 {len(live_dups)} + 魔法数 {len(live_magic)}）")
    if a.report:
        return 0
    return 0 if live == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
