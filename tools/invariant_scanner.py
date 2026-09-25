# -*- coding: utf-8 -*-
"""invariant_scanner.py — repo-wide 不变量扫描器（20260919 VKPS 评估卷 ROI 第一件，审计区造仪）
__version__ = "1.1"  # canonical 声明：本件为唯一权威版本（20260919 回执卡差额4 处置：
# 主区 混元/kernel主线/invariant_scanner.py 已由本版覆盖同步，任何他版镜像不得作判定依据）
三规则（评估卷第九章）之 1+2 通用实现（规则 3=登记表对账，由 refresh_99map.py 类脚本分表承担）：
  R1 每个 dataclass 字段必须 ≥1 个读取点（AST Attribute-Load 语境）→ 死字段候选
  R2 每个 check() 条件必须可被证伪 → hasattr 对本文件已知字段=恒真候选；字面恒真常量=恒真
输出「候选」而非定谳（getattr/序列化/生成器拼接用例须人读豁免）——③级可否证。
用法: py -X utf8 tools/invariant_scanner.py <file.py> [more.py ...]
"""
import ast, sys, collections

__version__ = "1.1"  # canonical 版本位（机读）；20260919 回执卡差额4 处置项
CANONICAL = True      # 本件为唯一权威版本；他版镜像不得作判定依据

def scan(path):
    src = open(path, encoding="utf-8", errors="replace").read()
    tree = ast.parse(src)
    findings = []

    # R1: dataclass 字段收集
    fields = {}  # field -> class name
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            is_dc = any((isinstance(d, ast.Name) and d.id == "dataclass") or
                        (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "dataclass")
                        for d in node.decorator_list)
            if not is_dc:
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields[stmt.target.id] = node.name

    # 全模块 Attribute-Load 计数 + 构造器 kw 注入统计（v1.1：混元线实测反馈
    # —— Report.notes 经构造器 kw 传入为真实写路径，v1.0 误报死字段；kw 注入型
    # 区分登记为"须人读豁免"而非死字段候选）
    loads = collections.Counter()
    kwin = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            loads[node.attr] += 1
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg:
                    kwin.add(kw.arg)
    # Name-Load（解包/直接引用字段名作变量极少见，不计，防误报方向=宁漏勿错）

    dead = {f: c for f, c in fields.items() if loads[f] == 0}
    for f, cls in sorted(dead.items()):
        if f in kwin:
            findings.append(("R1-kw", path,
                f"kw注入型零直读字段: {cls}.{f}（构造器 kw 传入在案、本文件 0 直读——"
                f"写入面存在，读取面或在序列化/外部，须人读豁免）"))
        else:
            findings.append(("R1", path, f"dataclass 死字段候选: {cls}.{f}（全文件 0 读取点）"))

    # R2: check() 条件可证伪性
    known_fields = set(fields)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "check":
            cond = node.args[1] if len(node.args) > 1 else None
            if cond is None:
                continue
            # 2a: hasattr(obj, "const") 且 const 为本文件已知 dataclass 字段 → 若 obj 是该字段所属类实例则恒真
            if isinstance(cond, ast.Call) and isinstance(cond.func, ast.Name) and cond.func.id == "hasattr":
                if len(cond.args) == 2 and isinstance(cond.args[1], ast.Constant) and isinstance(cond.args[1].value, str):
                    attr = cond.args[1].value
                    if attr in known_fields:
                        findings.append(("R2a", path,
                            f"恒真候选: check(..., hasattr(·, {attr!r})) @line {node.lineno} —— {attr} 为本文件已知 dataclass 字段（hasattr 恒真，不可证伪）"))
                    else:
                        findings.append(("R2a'", path,
                            f"hasattr 可证伪性存疑: check(..., hasattr(·, {attr!r})) @line {node.lineno}（attr 非本文件 dataclass 字段，若 obj 构造保证存在仍恒真——须人读）"))
            # 2b: 字面恒真常量
            if isinstance(cond, ast.Constant) and (cond.value is True or (cond.value not in (False, 0, None, "") and cond.value)):
                findings.append(("R2b", path, f"字面恒真: check(..., {cond.value!r}) @line {node.lineno}"))
            # 2c: 同名比较 a == a
            if isinstance(cond, ast.Compare) and len(cond.ops) == 1 and isinstance(cond.ops[0], ast.Eq):
                l, r = cond.left, cond.comparators[0]
                if isinstance(l, ast.Name) and isinstance(r, ast.Name) and l.id == r.id:
                    findings.append(("R2c", path, f"同名恒等比较: check(..., {l.id} == {r.id}) @line {node.lineno}"))
    return findings

def main():
    r2_only = "--r2-only" in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    allf = []
    for p in paths:
        try:
            f = scan(p)
            allf += [x for x in f if not r2_only or x[0].startswith("R2")]
        except SyntaxError as e:
            allf.append(("ERR", p, f"语法解析失败: {e}"))
    by = collections.Counter(r[0] for r in allf)
    if r2_only:
        # 供钩子消费：单行候选数（R2 族合计），findings 走 stderr
        print(f"R2_CANDIDATES={len(allf)}")
        for rule, path, msg in allf:
            print(f"[{rule}] {msg}", file=sys.stderr)
    else:
        for rule, path, msg in allf:
            print(f"[{rule}] {msg}  ({path})")
        print(f"\n=== 候选总数 {len(allf)} {dict(by)}（候选≠定谳：R1 须排除 getattr/序列化/生成器拼接用例；R2a' 须人读构造点） ===")
    sys.exit(2 if allf else 0)

if __name__ == "__main__":
    main()
