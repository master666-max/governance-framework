# verify_hy_pb2.py — 混元 P-B2 三臂独立复算（T2 验收，2026-09-16）
# 用法（W2-N8 起）: py -X utf8 tools/verify_hy_pb2.py <混元大审查仓路径>   （或设环境变量 AUDIT_NEST）
import json, os, subprocess, statistics, sys, math

# W2-N8（20260923 开工批）：外仓路径**不再写死**——原写死的 D 盘旧工作区路径已废，
# 写死会让 `git -C` 静默失败、`json.loads(b"")` 抛无头绪的解码错（看起来像数据坏，其实是路径没了）。
# 改为显式传参 + 存在性闸：缺参或路径不存在即 fail-closed 退出，不猜、不扫空、不吐假读数。
nest = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AUDIT_NEST", "")
if not nest:
    raise SystemExit("用法: py -X utf8 tools/verify_hy_pb2.py <混元大审查仓路径>"
                     "（或设 AUDIT_NEST）——原写死路径已废，拒绝猜路径")
if not os.path.isdir(nest):
    raise SystemExit(f"外仓路径不存在：{nest}（fail-closed：不扫空、不出假读数）")
r = subprocess.run(['git', '-C', nest, 'show',
                    '1bad251:混元/两线联合-EJ3EJ4-20260911/res_pb2.json'],
                   capture_output=True)
d = json.loads(r.stdout.decode('utf-8'))

k0 = list(d['reanchor_only'])[0]
v0 = d['reanchor_only'][k0]
print('seed字段:', sorted(v0.keys()))

def mean_sd(xs):
    return statistics.mean(xs), statistics.pstdev(xs)

arms = {}
for a in d:
    seeds = d[a]
    gt = [s['gain_true'] for s in seeds.values()]
    trig = None
    for key in ('reanchors', 'reverts', 'reanchor_events', 'revert_events'):
        if key in v0:
            trig = trig or 0
            trig += sum(s[key] for s in seeds.values())
    arms[a] = (gt, trig)
    m, sd = mean_sd(gt)
    print(f'{a}: n={len(gt)} 真值均值={m:+.4f} sd(ddof0)={sd:.4f} 触发合计={trig}')

ro = arms['reanchor_only'][0]
for a in ('restricted_revert', 'unconditional'):
    gt = arms[a][0]
    diffs = [x - y for x, y in zip(gt, ro)]
    md = statistics.mean(diffs)
    sd = statistics.pstdev(diffs)
    t = md / (sd / math.sqrt(len(diffs))) if sd > 0 else float('nan')
    se = sd / math.sqrt(len(diffs))
    print(f'{a} vs reanchor_only: 配对差={md:+.4f}±{se:.4f} t={t:.2f}')
