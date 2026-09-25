# verify_kernel_t15_best.py — 890 引擎定向验证（用户令，2026-09-16）
# ① T15 重锚计数膨胀：漂移世界逐审计分支记录，查重复重锚/判别式退化
# ② 爬升后回落轨迹 best 单调性：缓降/骤降两档 + rotate 隐藏重置路径
import importlib.util, os, random, statistics, sys

# W2-N8（20260923 开工批）：外仓路径不再写死（原值已废）；显式传参 + 存在性闸，fail-closed。
# 用法: py -X utf8 tools/verify_kernel_t15_best.py <混元大审查仓路径>   （或设 AUDIT_NEST）
NEST = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AUDIT_NEST", "")
if not NEST:
    raise SystemExit("用法: py -X utf8 tools/verify_kernel_t15_best.py <混元大审查仓路径>"
                     "（或设 AUDIT_NEST）——原写死路径已废，拒绝猜路径")
if not os.path.isdir(NEST):
    raise SystemExit(f"外仓路径不存在：{NEST}（fail-closed：不扫空、不出假读数）")

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = m          # dataclass 处理需要模块已注册
    spec.loader.exec_module(m)
    return m

KM = load('kernel', NEST + '/混元/kernel主线/kernel.py')   # 名字须为 kernel（vk_common 以 from kernel import 引用）
VC = load('vkc', NEST + '/混元/kernel主线/验收-W1/vk_common.py')
Kernel, KernelConfig, Policy, truth = KM.Kernel, KM.KernelConfig, KM.Policy, KM.truth
build_world = VC.build_world

LOG = []
_orig_audit = Kernel._audit
def patched_audit(self):
    pre_best, pre_pol, pre_ra = self._best_truth, self._best_policy, self.reanchors
    rv, cur = _orig_audit(self)
    if pre_best is None:
        branch = 'init'
    elif rv:
        branch = 'REVERT'
    elif self.reanchors > pre_ra:
        branch = 'REANCHOR'
    elif cur < pre_best - self.cfg.degrade_thr:
        branch = 'streak'
    else:
        branch = 'hold'
    LOG.append(dict(gen=self.generation, cur=round(cur, 4),
                    pre=None if pre_best is None else round(pre_best, 4),
                    post=None if self._best_truth is None else round(self._best_truth, 4),
                    branch=branch, streak=self._degrade_streak,
                    pol_same=pre_pol is self.champion if pre_best is not None else None))
    return rv, cur
Kernel._audit = patched_audit

def mk(seed, **cfgkw):
    rnd0 = random.Random(seed)
    es = build_world(seed)
    tasks = [f"T{i} K{i % 6}" for i in range(16)]
    held = [f"T{i} K{(i + 3) % 6}" for i in range(3, 19)]
    return Kernel(entries=es, tasks_train=tasks, tasks_held=held,
                  rnd=random.Random(seed), cfg=KernelConfig(**cfgkw))

def run_t15(seed, ra_after, gens=24, drift=0.35):
    LOG.clear()
    kk = mk(seed, scale=3.0, audit=True, reanchor_after=ra_after)
    for g in range(1, gens + 1):
        if g == gens // 3:
            r = random.Random(seed + 999)
            for e in kk.entries:
                if r.random() < drift:
                    e.quality = random.Random(seed * 100 + g + int(e.id[1:]) if e.id.startswith('e') else 0).random() * 0.3 \
                        if False else r.random() * 0.3
        kk._step(g)
    return list(LOG), kk.reanchors

print('════ ① T15 重锚计数（ra_after=1，套件同参，12 种子）════')
tot_ra = tot_deg = tot_reanchor_branch = 0
episodes = []
for s in range(1, 13):
    log, ra = run_t15(s, 1)
    reanch = [r for r in log if r['branch'] == 'REANCHOR']
    deg = [r for r in log if r['branch'] in ('REANCHOR', 'streak', 'REVERT')]
    tot_ra += ra; tot_deg += len(deg)
    gens_r = [r['gen'] for r in reanch]
    consecutive = any(b - a <= 5 for a, b in zip(gens_r, gens_r[1:]))  # audit_every=5 → 相邻审计即重锚
    # 判别式退化检查：重锚后 _best_policy 与 champion 是否同源（pol_same 于重锚后首次退化审计）
    episodes.append((s, ra, gens_r, len(deg), consecutive))
    print(f' seed{s:2d}: reanchors={ra} 重锚@gen={gens_r} 退化审计={len(deg)}次 连发(≤1审计间隔)={consecutive}')
print(f'合计: reanchors={tot_ra} / 退化审计={tot_deg} → 每次退化审计的重锚转化率={tot_ra/max(tot_deg,1):.2f}')

print('\n════ ①b 默认 ra_after=2（K-24 死路验证）════')
for s in (1, 2, 3):
    log, ra = run_t15(s, 2)
    branches = [(r['gen'], r['branch']) for r in log]
    print(f' seed{s}: reanchors={ra} 分支序列={branches}')

print('\n════ ② 爬升后回落 best 单调性（构造世界）════')
def run_risefall(seed, fall_mode, gens=24):
    LOG.clear()
    kk = mk(seed, scale=3.0, audit=True, reanchor_after=2)
    q0 = {e.id: e.quality for e in kk.entries}
    for g in range(1, gens + 1):
        for e in kk.entries:
            if g <= 12:   # 爬升段
                e.quality = min(1.0, q0[e.id] + 0.035 * g)
            elif fall_mode == 'slow':      # 每代 -0.5%（每审计间隔≈2.5%>thr 但分代缓）
                e.quality = max(0.0, (q0[e.id] + 0.035 * 12) * (0.995 ** (g - 12)))
            else:                          # step：g=13 一步砍 40%
                e.quality = (q0[e.id] + 0.035 * 12) * (0.6 if g >= 13 else 1.0)
        kk._step(g)
    audits = [r for r in LOG if r['gen'] % 5 == 0 or r['branch'] == 'init']
    return audits

for mode in ('slow', 'step'):
    print(f'--- fall_mode={mode} ---')
    viol_reanchor = viol_init = viol_revert = holds = 0
    for s in (1, 2, 3, 4):
        audits = run_risefall(s, mode)
        seq = [(r['gen'], r['branch'], r['post'], r['cur']) for r in audits if r['post'] is not None]
        # 有效 best 序列（含 init 路径）：post[t] < post[t-1] 即有效单调破坏
        drops = [(seq[i][0], seq[i][1], seq[i-1][2], seq[i][2])
                 for i in range(1, len(seq)) if seq[i][2] < seq[i-1][2] - 1e-9]
        v_ra = sum(1 for d in drops if d[1] == 'REANCHOR')
        v_in = sum(1 for d in drops if d[1] == 'init')
        v_rv = sum(1 for d in drops if d[1] == 'REVERT')
        viol_reanchor += v_ra; viol_init += v_in; viol_revert += v_rv
        holds += sum(1 for g, b, p, c in seq if b == 'hold')
        print(f' seed{s}: 有效best序列={[(g, round(p, 3)) for g, b, p, c in seq]}')
        print(f'   有效下降={len(drops)} (重锚={v_ra}, rotate隐藏init={v_in}, revert={v_rv})')
        for d in drops:
            print(f'   ↓ gen{d[0]} [{d[1]}] best {round(d[2], 4)} → {round(d[3], 4)}')
    print(f' 小计: 重锚致降={viol_reanchor} rotate隐藏致降={viol_init} revert致降={viol_revert} hold维持={holds}')

print('\n════ ①c 判别式退化检查（T15 ra_after=1：重锚后 _best_policy 与 champion 同源性）════')
for s in (1, 7, 8):
    log, ra = run_t15(s, 1)
    deg = [(r['gen'], r['branch'], r['pol_same']) for r in log if r['branch'] in ('REANCHOR', 'streak')]
    print(f' seed{s}: 退化审计(gen,分支,审计前_best_policy≡champion?)={deg}')
