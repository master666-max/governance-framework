# verify_doubao_anchor.py — 豆包 E92 锚定行逐列比对 v2（第四任验收，2026-09-16）
# 口径：r15 表只保留 r13 的 5/7 列（砍「热区占比」「诚实降级丢弃」）。
# 锚定主张 = 保留列逐位≡r13。auth 行不在锚定面（语义已修复，预期不同）。
import subprocess, re

# W2-N8（20260923 开工批）：外仓路径不再靠 glob 猜——原 `glob.glob(...)[0]` 猜不中即 IndexError，
# 报错形态看不出「路径没了」。改为显式传参 + 存在性闸（fail-closed：不扫空、不出假读数）。
# 用法: py -X utf8 tools/verify_doubao_anchor.py <大审查仓路径>   （或设环境变量 AUDIT_NEST）
import os as _os, sys as _sys
nest = _sys.argv[1] if len(_sys.argv) > 1 else _os.environ.get("AUDIT_NEST", "")
if not nest:
    raise SystemExit("用法: py -X utf8 tools/verify_doubao_anchor.py <大审查仓路径>（或设 AUDIT_NEST）——原按通配符猜路径的做法已废，拒绝猜")
if not _os.path.isdir(nest):
    raise SystemExit(f"外仓路径不存在：{nest}（fail-closed：不扫空、不出假读数）")

def show(p):
    return subprocess.run(['git', '-C', nest, 'show', p], capture_output=True,
                          text=True, encoding='utf-8', errors='replace').stdout

r15 = show('1c77112:豆包/memevo/results_round15.txt')
r13 = show('1c77112:豆包/memevo/results_round13.txt')

def parse_e92(txt):
    """返回 {(防御,参数): [φ,recall,污染,幻影,golden]}，只取 E92 段。"""
    seg = txt.split('### E92')[1].split('###')[0] if '### E92' in txt else txt
    out = {}
    for L in seg.splitlines():
        t = L.split()
        if t and t[0] in ('auth', 'authdrop', 'none', 'ratelimit') and len(t) >= 6:
            nums = [x for x in t[2:] if re.fullmatch(r'-?\d+\.?\d*', x)]
            if len(nums) == 5:
                out[(t[0], t[1])] = nums
    return out

def parse_e80_rows(txt):
    """r13 E80 表：返回 {(防御,参数): [φ,recall,污染,热区,幻影,降级,golden]}"""
    seg = txt.split('### E80')[1].split('###')[0]
    out = {}
    for L in seg.splitlines():
        t = L.split()
        if t and t[0] in ('auth', 'authdrop', 'none', 'ratelimit') and len(t) >= 8:
            nums = [x for x in t[2:] if re.fullmatch(r'-?\d+\.?\d*', x)]
            if len(nums) == 7:
                out[(t[0], t[1])] = nums
    return out

a, b = parse_e92(r15), parse_e80_rows(r13)
print(f'r15 E92 行数={len(a)}  r13 E80 行数={len(b)}')
ok_all = True
for k in sorted(a):
    v15 = a[k]
    if k not in b:
        print(f'  [!] {k}: r13 无对应行'); ok_all = False; continue
    v13 = b[k]
    # r13 列序: φ,recall,污染,热区,幻影,降级,golden → 取共享5列
    v13_shared = [v13[0], v13[1], v13[2], v13[4], v13[6]]
    hit = (v15 == v13_shared)
    ok_all &= hit
    tag = 'OK' if hit else 'MISS'
    print(f'  [{tag}] {k[0]:10s} {k[1]:8s} r15={v15} r13共享列={v13_shared}')
print('E92 锚定面(保留5列):', 'ALL PASS' if ok_all else 'FAIL')
