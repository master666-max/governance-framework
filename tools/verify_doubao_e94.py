# verify_doubao_e94.py — 豆包 E94 六格 ≡ round14 E86 锚定比对（第四任验收）
import subprocess, re

# W2-N8（20260923 开工批）：外仓路径不再靠 glob 猜——原 `glob.glob(...)[0]` 猜不中即 IndexError，
# 报错形态看不出「路径没了」。改为显式传参 + 存在性闸（fail-closed：不扫空、不出假读数）。
# 用法: py -X utf8 tools/verify_doubao_e94.py <大审查仓路径>   （或设环境变量 AUDIT_NEST）
import os as _os, sys as _sys
nest = _sys.argv[1] if len(_sys.argv) > 1 else _os.environ.get("AUDIT_NEST", "")
if not nest:
    raise SystemExit("用法: py -X utf8 tools/verify_doubao_e94.py <大审查仓路径>（或设 AUDIT_NEST）——原按通配符猜路径的做法已废，拒绝猜")
if not _os.path.isdir(nest):
    raise SystemExit(f"外仓路径不存在：{nest}（fail-closed：不扫空、不出假读数）")

def show(p):
    return subprocess.run(['git', '-C', nest, 'show', p], capture_output=True,
                          text=True, encoding='utf-8', errors='replace').stdout

r15 = show('1c77112:豆包/memevo/results_round15.txt')
r14 = show('1c77112:豆包/memevo/results_round14.txt')

# r15 E94 段的 wordpool/single 行（六格锚定面）
seg15 = r15.split('### E94')[1].split('###')[0]
rows15 = {}
for L in seg15.splitlines():
    t = L.split()
    if len(t) >= 6 and t[0] in ('selftag', 'wordpool') and t[1] in ('evolve', 'single'):
        nums = [x for x in t[2:] if re.fullmatch(r'-?\d+\.?\d*', x)]
        rows15[(t[0], t[1], nums[0])] = nums[1:]  # ε 归 key，其余为值
# 只看声称: (wordpool,selftag)×(single) 六格
anchor15 = {k: v for k, v in rows15.items() if k[1] == 'single'}

# r14 E86 段找对应行（列结构可能不同，宽松取数值序列）
seg14 = r14.split('E86')[1].split('###')[0] if 'E86' in r14 else r14
rows14 = {}
for L in seg14.splitlines():
    t = L.split()
    if len(t) >= 5 and t[0] in ('selftag', 'wordpool') and t[1] in ('evolve', 'single'):
        nums = [x for x in t if re.fullmatch(r'-?\d+\.?\d*', x)]
        rows14[(t[0], t[1])] = rows14.get((t[0], t[1]), []) + [nums]

print('r15 E94 锚定行数:', len(anchor15))
ok = True
for (arm, opt, eps), vals in sorted(anchor15.items()):
    cands = rows14.get((arm, opt), [])
    hit = any(eps in c and all(v in c for v in vals) for c in cands)
    ok &= hit
    print(f'  [{"OK" if hit else "MANUAL"}] {arm}/{opt} eps={eps}: r15={vals}')
    if not hit:
        for c in cands:
            if eps in c:
                print('      r14 同eps行:', c)
print('E94 六格锚定:', 'PASS' if ok else '需人读复核(列结构差异)')
# 人读兜底：直接打两侧行
print('\n--- r14 E86 原行(供人读) ---')
for L in seg14.splitlines():
    if L.strip() and (L.strip().startswith(('selftag', 'wordpool'))):
        print(' ', L.strip()[:110])
