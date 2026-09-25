# verify_t1_hy.py — 混元 T1 交付数字独立复算（第四任验收用，2026-09-16）
# 对象：res_pb1.json (18b3513) / res_ej4v2.json (2cd5426)
# 方法：从结果 json 独立复算报告宣称的判定数字，不信任报告文本。
import json, statistics, math

# W2-N8（20260923 开工批）：外仓路径不再靠 glob 猜——原 `glob.glob(...)[0]` 猜不中即 IndexError，
# 报错形态看不出「路径没了」。改为显式传参 + 存在性闸（fail-closed：不扫空、不出假读数）。
# 用法: py -X utf8 tools/verify_t1_hy.py <大审查仓路径>   （或设环境变量 AUDIT_NEST）
import os as _os, sys as _sys
base = _sys.argv[1] if len(_sys.argv) > 1 else _os.environ.get("AUDIT_NEST", "")
if not base:
    raise SystemExit("用法: py -X utf8 tools/verify_t1_hy.py <大审查仓路径>（或设 AUDIT_NEST）——原按通配符猜路径的做法已废，拒绝猜")
if not _os.path.isdir(base):
    raise SystemExit(f"外仓路径不存在：{base}（fail-closed：不扫空、不出假读数）")
ok_all = True

def check(label, recomputed, claimed, tol=1e-4):
    global ok_all
    hit = abs(recomputed - claimed) <= tol
    ok_all &= hit
    print(f'  [{"OK" if hit else "MISS"}] {label}: 复算={recomputed:.4f} 报告={claimed:.4f}')

# ---------- P-B1: 2 臂 x 8 种子 ----------
print('== P-B1 (res_pb1.json) ==')
d1 = json.load(open(base + '/res_pb1.json', encoding='utf-8'))
GENS = 24  # 报告口径: 2 臂 x 8 种子 x 24 代
for arm, c_gt, c_sd, c_judge, c_poison in (
        ('full3',    0.3924, 0.1359, 0.1505, 0.25),
        ('blind_ctl', 0.4027, 0.1393, 0.3996, 0.27)):
    seeds = d1[arm]
    gt = [s['gain_true'] for s in seeds.values()]
    gj = [s['gain_train_judge'] for s in seeds.values()]
    pg = [s['poison_champion_gens'] for s in seeds.values()]
    print(f' {arm} (n={len(seeds)}):')
    check('gain_true 均值', statistics.mean(gt), c_gt)
    check('gain_true sd(ddof=0)', statistics.pstdev(gt), c_sd, 1e-3)
    check('gain_train_judge 均值', statistics.mean(gj), c_judge)
    poison_ratio = sum(pg) / (len(seeds) * GENS)
    check('毒champion代占比', poison_ratio, c_poison, 1e-3)

# 配对差 t（成对 t 检验，同种子配对）
gt_f = [d1['full3'][k]['gain_true'] for k in sorted(d1['full3'])]
gt_b = [d1['blind_ctl'][k]['gain_true'] for k in sorted(d1['blind_ctl'])]
diffs = [b - f for f, b in zip(gt_f, gt_b)]
md = statistics.mean(diffs)
sd = statistics.stdev(diffs)
t = md / (sd / math.sqrt(len(diffs)))
print(f' 盲评-全开配对差: 均值={md:.4f} t={t:.3f}  (报告: +0.0102, t=2.01)')
check('配对差均值', md, 0.0102, 1e-3)

# H-A / H-B 机械判定复核
ha = 'NOT SUPPORTED' if statistics.mean(gt_f) >= 0 else 'pending'
print(f' H-A 复核: full3 真值增益={statistics.mean(gt_f):+.4f} >= 0 -> {ha} (报告: NOT SUPPORTED)')

# ---------- E-J4 v2: 9 臂 x 6 种子 ----------
print('\n== E-J4 v2 (res_ej4v2.json) ==')
d2 = json.load(open(base + '/res_ej4v2.json', encoding='utf-8'))
rows = d2['full']

def arm_of(r):
    # 字段实证：prompt=制式(abs/rubric), scene=注入场景, boost=放大器
    pr, sc, bo = r['prompt'], r['scene'], r.get('boost', False)
    if pr != 'abs':
        return f'rubric/{sc}'
    return f'abs/{sc}/boost' if bo else f'abs/{sc}'

arms = {}
for r in rows:
    arms.setdefault(arm_of(r), []).append(r)

claimed = {  # (gain_true 均值, gap 均值, 检出数/6)
    'abs/clean':       (-0.0608, 0.1558, 0),
    'abs/judge':       (-0.0833, 0.1073, 6),
    'abs/judge/boost': (-0.1008, 0.1394, 6),
    'abs/both':        (-0.0942, 0.1150, 6),
    'abs/world':       (-0.0608, 0.1558, 0),
}
for a, rs in sorted(arms.items()):
    gt = [r['gain_true'] for r in rs]
    gap = [r['self_real_gap'] for r in rs]
    fires = [r for r in rs if r.get('anchor_fire_dir')]
    dirs = {}
    for r in fires:
        dirs[r['anchor_fire_dir']] = dirs.get(r['anchor_fire_dir'], 0) + 1
    se = statistics.stdev(gt) / math.sqrt(len(gt))
    print(f' {a} (n={len(rs)}): 真值={statistics.mean(gt):+.4f}±{se:.4f} '
          f'gap={statistics.mean(gap):.4f} 检出={len(fires)}/{len(rs)} 方向={dirs}')
    if a in claimed:
        cg, cp, cf = claimed[a]
        check(f'{a} 真值均值', statistics.mean(gt), cg, 1e-3)
        check(f'{a} gap均值', statistics.mean(gap), cp, 1e-3)
        hit = (len(fires) == cf)
        ok_all &= hit
        print(f'    [{"OK" if hit else "MISS"}] 检出数: 复算={len(fires)} 报告={cf}')

up_total = sum(1 for r in rows if r.get('anchor_fire_dir') == 'up')
down_total = sum(1 for r in rows if r.get('anchor_fire_dir') == 'down')
print(f' 检出方向分布: up={up_total} down={down_total}  (报告: up=18 / down=0)')
ok_all &= (up_total == 18 and down_total == 0)

# abs/world 锚定流 drift 段恒 0.700 取证（报告: g7-g12 八位小数不动）
world_rows = arms.get('abs/world', [])
for r in world_rows:
    st = r.get('anchor_stream')
    if isinstance(st, list) and len(st) >= 13:
        seg = st[7:13]
        print(f' world seed={r.get("seed")} 锚定流 g7-g12: {seg}')
        break

print('\n总体:', 'ALL-OK' if ok_all else '存在 MISS——逐项核查')
