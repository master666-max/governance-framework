# -*- coding: utf-8 -*-
"""S1_verify_behavior.py — 层3 机械验收：旧版（git 基准）vs evocore 同输入行为对拍

设计（S1 设计件 §4 层3）：
  旧侧 = `git show <base>:memsys/...` 四件提取到临时目录（平铺裸名导入，与原样一致）；
  新侧 = 仓库内 evocore 包；
  两侧**各自子进程**载入（避免模块名串扰），跑同一套用例，输出 canonical JSON，
  逐用例 sha256 比对——差异=0 才 PASS。

确定性处理（唯一规范化，如实声明）：
  * 决策留痕 dict 的 "ts" 字段用真实时钟（_now()）——两侧替换为 `<ts>`（并校验
    形如 YYYY-MM-DDTHH:MM:SS，形状不合记 `<ts-bad:...>`）——**只规范化该字段**；
  * 异常以 (类型名, 消息) 参与比对；
  * **加法式新增键**（`ADDITIVE_KEYS`，S8-5② 起）：基准侧（老实现）没有这些键，直接比 sha
    会把"新增字段"误判成"行为变更"，故比对前递归剔除——登记是显式的，且带**反空转闸**：
    登记的键若不再出现在新侧输出，本工具判红（过期登记=给该键开了永久豁免）。

用法: py -X utf8 tools/S1_verify_behavior.py [--base b19c9a4] [--repo <路径>]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

# 加法式新增键登记（键名 → 引入批次）。剔除只作用于比对，不改任何真实值；其余差异照抓。
ADDITIVE_KEYS = ("prereg",)          # S8-5②（20260923）：决策留痕的判据指针


def _norm(r):
    """递归剔除 ADDITIVE_KEYS 登记的键（比对用）。"""
    if isinstance(r, dict):
        return {k: _norm(v) for k, v in r.items() if k not in ADDITIVE_KEYS}
    if isinstance(r, (list, tuple)):
        return [_norm(x) for x in r]
    return r


def _collect_keys(r, out):
    """收集输出里实际出现过的登记键（反空转闸用）。"""
    if isinstance(r, dict):
        for k, v in r.items():
            if k in ADDITIVE_KEYS:
                out.add(k)
            _collect_keys(v, out)
    elif isinstance(r, (list, tuple)):
        for x in r:
            _collect_keys(x, out)

_OLD_FILES = {"tunables": "memsys/tunables.py", "retrieval": "memsys/engine/retrieval.py",
              "lifecycle": "memsys/engine/lifecycle.py", "decision": "memsys/engine/decision.py"}


def _canon(x):
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if k == "ts":
                out[k] = "<ts>" if isinstance(v, str) and _TS.match(v) else f"<ts-bad:{v!r}>"
            else:
                out[k] = _canon(v)
        return out
    if isinstance(x, (list, tuple)):
        return [_canon(v) for v in x]
    return x


def _case(mods, name, fn, *args):
    try:
        return name, _canon(fn(mods, *args))
    except Exception as e:                       # 异常即结果的一部分（类型+消息参与比对）
        return name, ["EXC", type(e).__name__, str(e)]


def _entry(**kw):
    base = {"id": "e1", "content": "用户偏好深色主题", "keywords": ["偏好"], "importance": 5,
            "created_at": "2026-09-20T00:00:00", "type": "semantic", "state": "intermediate"}
    base.update(kw)
    return base


def _battery(mods):
    """全部用例（同一份代码，两侧执行——差异只能来自被载入库）。"""
    r, l, d, t = mods.retrieval, mods.lifecycle, mods.decision, mods.tunables
    import datetime
    now = datetime.datetime(2026, 9, 21, 12, 0, 0)
    cases = []
    cases.append(_case(mods, "tokens_cjk_west", lambda m: r._tokens("API Token 深色主题混合")))
    cases.append(_case(mods, "tokens_empty", lambda m: r._tokens("")))
    cases.append(_case(mods, "tokens_single_cjk", lambda m: r._tokens("好")))
    cases.append(_case(mods, "score_basic", lambda m: r.score(_entry(), "偏好", t.DEFAULTS, now)))
    cases.append(_case(mods, "score_filter_zero_off",
                       lambda m: r.score(_entry(content="无关内容", keywords=["无关"]),
                                         "偏好", t.Tunables(filter_zero=0), now)))
    cases.append(_case(mods, "score_filter_zero_on",
                       lambda m: r.score(_entry(content="无关内容", keywords=["无关"]),
                                         "偏好", t.DEFAULTS, now)))
    cases.append(_case(mods, "score_types",
                       lambda m: [r.score(_entry(type=ty, created_at="2026-08-12T12:00:00"), "偏好", t.DEFAULTS, now)
                                  for ty in ("episodic", "semantic", "procedural", "未知")]))
    cases.append(_case(mods, "score_last_used",
                       lambda m: r.score(_entry(created_at="2026-01-01T00:00:00",
                                                last_used_at="2026-09-21T00:00:00"), "偏好", t.DEFAULTS, now)))
    cases.append(_case(mods, "score_bad_ts",
                       lambda m: r.score(_entry(created_at="not-a-date"), "偏好", t.DEFAULTS, now)))
    cases.append(_case(mods, "score_z_suffix",
                       lambda m: r.score(_entry(created_at="2026-09-20T00:00:00Z"), "偏好", t.DEFAULTS, now)))
    cases.append(_case(mods, "score_tombstone",
                       lambda m: r.score(_entry(tombstone=True), "偏好", t.DEFAULTS, now)))
    cases.append(_case(mods, "score_importance_zero_and_ten",
                       lambda m: [r.score(_entry(importance=i), "偏好", t.DEFAULTS, now) for i in (0, 10)]))
    cases.append(_case(mods, "score_custom_tunables",
                       lambda m: r.score(_entry(), "偏好", t.Tunables(w_kw=1.0, w_content=0.5, w_imp=0.0), now)))
    cases.append(_case(mods, "recall_passthrough", lambda m: r.recall([_entry()], "偏好")))
    cases.append(_case(mods, "retrieve_tie_break",
                       lambda m: [e["id"] for _, e in r.retrieve(
                           [_entry(id="b1", content="偏好", created_at="2026-09-21T12:00:00"),
                            _entry(id="a1", content="偏好", created_at="2026-09-21T12:00:00")],
                           "偏好", k=5, now=now)]))
    cases.append(_case(mods, "retrieve_empty", lambda m: r.retrieve([], "偏好", k=5, now=now)))
    cases.append(_case(mods, "retrieve_single_and_k_trunc",
                       lambda m: [e["id"] for _, e in r.retrieve(
                           [_entry(id="x1"), _entry(id="x2", content="深色")], "偏好", k=1, now=now)]))
    cases.append(_case(mods, "retrieve_custom_recall_fn",
                       lambda m: r.retrieve([_entry(id="hit", content="偏好"), _entry(id="miss")], "偏好", k=5,
                                            now=now, recall_fn=lambda es, q, **kw: [es[0]])))
    cases.append(_case(mods, "route_boundary",
                       lambda m: [l.route(_entry(importance=i)) for i in (0, 6, 7, 8)]))
    cases.append(_case(mods, "route_custom_threshold",
                       lambda m: l.route(_entry(importance=5), t.Tunables(promote_importance_min=5))))
    cases.append(_case(mods, "promote_from_attic_raises",
                       lambda m: l.promote(_entry(state="attic"))))
    cases.append(_case(mods, "promote_ok", lambda m: l.promote(_entry(id="p1"))))
    cases.append(_case(mods, "attic_tombstone_touch_events",
                       lambda m: [l.attic(_entry(id="a1"), "降权理由" * 40), l.tombstone(_entry(id="t1")),
                                  l.touch(_entry(id="u1"), "2026-09-21T00:00:00")]))
    cases.append(_case(mods, "decay_multiplier_all",
                       lambda m: [l.decay_multiplier(_entry(type=ty))
                                  for ty in ("episodic", "semantic", "procedural", "未知")]))
    cases.append(_case(mods, "conflict_two", lambda m: d.adjudicate_conflict(
        [_entry(id="old", importance=9, created_at="2026-01-01T00:00:00"),
         _entry(id="new", importance=9, created_at="2026-09-21T00:00:00")])))
    cases.append(_case(mods, "conflict_manual_priority", lambda m: d.adjudicate_conflict(
        [_entry(id="hi", importance=10), _entry(id="man", importance=1, source="manual")])))
    cases.append(_case(mods, "conflict_lt2_raises", lambda m: d.adjudicate_conflict([_entry()])))
    cases.append(_case(mods, "merge_two_defer", lambda m: d.adjudicate_merge(
        [_entry(id="m1"), _entry(id="m2", source="manual")])))
    cases.append(_case(mods, "merge_single_raises", lambda m: d.adjudicate_merge([_entry()])))
    cases.append(_case(mods, "promote_batch", lambda m: d.adjudicate_promote(
        [_entry(id="p3", importance=3), _entry(id="p7", importance=7), _entry(id="p9", importance=9)])))
    cases.append(_case(mods, "tunables_bad_w_kw_raises", lambda m: t.Tunables(w_kw=0.0)))
    cases.append(_case(mods, "tunables_bad_filter_zero_raises", lambda m: t.Tunables(filter_zero=2)))
    cases.append(_case(mods, "big_deterministic_batch", lambda m: _batch(r, t, now)))
    return cases


def _batch(r, t, now):
    """50 条确定性伪随机条目 → 全量 (id, score) 序列（覆盖多参数组合）。"""
    import random
    rng = random.Random(7)
    types = ("episodic", "semantic", "procedural", "未知")
    ents = []
    for i in range(50):
        ents.append({"id": f"b{i:02d}", "content": rng.choice(["偏好 深色 主题", "无关 词面", "深色 设置"]),
                     "keywords": rng.choice([["偏好"], ["深色"], ["主题", "偏好"], []]),
                     "importance": rng.randint(0, 10), "type": rng.choice(types),
                     "created_at": f"2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}T00:00:00",
                     "state": rng.choice(["intermediate", "longterm", "attic"])})
    scored = [(e["id"], r.score(e, "偏好 深色", t.DEFAULTS, now)) for e in ents]
    return sorted(scored, key=lambda kv: (-kv[1], kv[0]))


def _load(mods_dir, which):
    sys.path.insert(0, mods_dir)
    if which == "old":
        import tunables, retrieval, lifecycle, decision
    else:
        from evocore import tunables, retrieval, lifecycle, decision
    return SimpleNamespace(tunables=tunables, retrieval=retrieval, lifecycle=lifecycle, decision=decision)


def main():
    if "--phase" in sys.argv:
        i = sys.argv.index("--phase")
        which, mods_dir, out = sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3]
        mods = _load(mods_dir, which)
        rows = [[name, res] for name, res in _battery(mods)]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, sort_keys=True)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="b19c9a4")
    ap.add_argument("--repo", default=os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        old_dir = os.path.join(td, "old")
        os.makedirs(old_dir)
        for name, rel in _OLD_FILES.items():
            out = subprocess.run(["git", "-C", a.repo, "show", f"{a.base}:{rel}"],
                                 capture_output=True, text=True, encoding="utf-8")
            if out.returncode != 0:
                raise SystemExit(f"git show 失败：{a.base}:{rel}\n{out.stderr}")
            with open(os.path.join(old_dir, f"{name}.py"), "w", encoding="utf-8", newline="\n") as f:
                f.write(out.stdout)
        p_old = os.path.join(td, "old.json")
        p_new = os.path.join(td, "new.json")
        me = os.path.abspath(__file__)
        for which, mdir, outp in (("old", old_dir, p_old), ("new", a.repo, p_new)):
            sub = subprocess.run([sys.executable, "-X", "utf8", me, "--phase", which, mdir, outp],
                                 capture_output=True, text=True, encoding="utf-8")
            if sub.returncode != 0:
                raise SystemExit(f"子进程 {which} 失败：\n{sub.stdout}\n{sub.stderr}")
        old = json.load(open(p_old, encoding="utf-8"))
        new = json.load(open(p_new, encoding="utf-8"))
    assert [n for n, _ in old] == [n for n, _ in new], "两侧用例清单不一致"
    diff = 0
    sha_map = {}
    for (n1, r1), (n2, r2) in zip(old, new):
        s1 = hashlib.sha256(json.dumps(_norm(r1), ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
        s2 = hashlib.sha256(json.dumps(_norm(r2), ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
        sha_map[n1] = s1
        if s1 != s2:
            diff += 1
            print(f"  ✗ {n1}: old={s1} new={s2}\n      old={json.dumps(r1, ensure_ascii=False)[:200]}"
                  f"\n      new={json.dumps(r2, ensure_ascii=False)[:200]}")
        else:
            print(f"  OK  {n1:32s} sha={s1}")
    # 反空转：登记的加法式键必须**真的出现在新侧输出**——否则登记已过期，而过期登记
    # 等于给该键开了永久豁免（"没查"与"查了没问题"同形），故判红而不是忽略。
    seen = set()
    _collect_keys(new, seen)
    stale = [k for k in ADDITIVE_KEYS if k not in seen]
    if stale:
        raise SystemExit(f"FAIL 加法式键登记过期：{stale} 未出现在新侧输出——请删除 "
                         f"ADDITIVE_KEYS 中的登记（留着等于给这些键开永久豁免）")
    if ADDITIVE_KEYS:
        print(f"  [注] 已归一化剔除加法式新增键 {list(ADDITIVE_KEYS)}（S8-5②）；其余差异照抓")
    # 空转防护：以下对**预期应相异**；若同 sha 说明夹具失效（"查了没差异"与"没查"同形）
    differ_pairs = [("score_filter_zero_off", "score_filter_zero_on"),
                    ("score_basic", "score_tombstone"),
                    ("score_basic", "tokens_cjk_west"),
                    ("route_boundary", "decay_multiplier_all"),
                    ("conflict_two", "merge_two_defer")]
    vacuous = [p for p in differ_pairs if sha_map.get(p[0]) == sha_map.get(p[1])]
    for p in vacuous:
        print(f"  ⚠ VACUOUS 预期相异但同 sha：{p[0]} == {p[1]}")
    print(f"\n用例 {len(old)} · 差异 {diff} · 空转对 {len(vacuous)}")
    verdict = (diff == 0 and not vacuous)
    print("层3 判定：" + ("PASS" if verdict else "FAIL"))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
