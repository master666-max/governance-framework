# -*- coding: utf-8 -*-
"""conformance.py — 内核接口与宿主契约一致性测试（SPEC v1 §E，20260923）
三种形态实跑：
  py -X utf8 audit-kit/conformance.py --kernel audit-kit --host memsys
  py -X utf8 audit-kit/conformance.py --fused evo-seat/evo_seat.py
  py -X utf8 audit-kit/conformance.py --kb <中库目录>          # S3/T4：中库形态（§K 六查）
检查：§A 内核符号 + §D 跨形态语义（临时库实跑）+（--host）§B 宿主三件事；--kb 追加中库形态。
检查器纪律：--kb 对被测物**只读**（链重放自行读 SQLite 复算，不开写连接——不改被测库）。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS: list[tuple[str, bool, str]] = []
_ERR_SNIPPET = 120          # 失败证据摘录长度（S3/T4：原裸值 120 命名化）


def _tamper_events(db: str, actor: str = "human:root") -> None:
    """绕过触发器篡改 events 头部字段（自测用），随即原位恢复触发器。
    S3/T4 去重：重装形态与融合形态的 §D 自测共用同一实现（原两处逐字重复）。"""
    conn = sqlite3.connect(db)
    conn.executescript("DROP TRIGGER no_update; DROP TRIGGER no_delete;")
    conn.execute("UPDATE events SET actor=?", (actor,))
    conn.executescript("CREATE TRIGGER no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'x'); END;"
                       "CREATE TRIGGER no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'x'); END;")
    conn.commit()
    conn.close()

def check(name: str, ok: bool, evidence: str = "") -> None:
    RESULTS.append((name, ok, evidence))


def note(name: str, evidence: str = "") -> None:
    """三态纪律（S3/T4）：N/A/SKIP 与 PASS **不同形**——打印为 [N/A]、不计入 PASS 分子。
    "这一格没被检查过"不许读成"检查通过了"（本项目判据设计的出发点）。"""
    RESULTS.append((name, None, evidence))

def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m   # dataclass 模块先注册再 exec（HANDOVER 坑 12）
    spec.loader.exec_module(m)
    return m

def _kernel_dirs(kernel: str):
    """内核根 → (core 目录, ledger 目录, 需注入 sys.path 的路径表)。
    两种布局（S2 装配器产物需要）：
      * 镜像树（root/core + root/ledger）——仓库态与 vendored/server 产物；
      * 平铺（root 自身含 ledger.py）——pypkg 产物的 _payload。
    """
    root = kernel if os.path.isabs(kernel) else os.path.join(AUD, kernel)
    core, led = os.path.join(root, "core"), os.path.join(root, "ledger")
    if os.path.isdir(core) and os.path.isdir(led):
        return core, led, [core, led]
    if os.path.isfile(os.path.join(root, "ledger.py")):
        return root, root, [root]
    raise SystemExit(f"内核根无法定位（无 core/+ledger/ 也无 ledger.py）：{root}")

def check_kernel_auditkit(host: str | None, kernel: str = "audit-kit"):
    core, led, inject = _kernel_dirs(kernel)
    sys.path[:0] = inject
    lg = _load(os.path.join(led, "ledger.py"), "ledger")
    for sym in ("open", "append", "verify", "count", "head", "rows"):
        check(f"§A Ledger.{sym}", callable(getattr(lg.Ledger, sym, None)))
    tmp = os.path.join(tempfile.mkdtemp(), "c.db")
    led_ = lg.Ledger.open(tmp)
    cap_mod = _load(os.path.join(core, "capabilities.py"), "capabilities")
    gt = _load(os.path.join(core, "gov_types.py"), "gov_types")
    cap = gt.Capability("memory", gt.PathGlobScope("*", "table"), frozenset({"append_events"}))
    led_.append(cap, "ci:conf", "t", {"a": 1})
    check("§D append 可用", led_.count() == 1)
    conn = sqlite3.connect(tmp)
    aborted = False
    try:
        conn.execute("UPDATE events SET kind='x'")
    except sqlite3.IntegrityError:
        aborted = True
    check("§D 触发器 ABORT", aborted, "UPDATE 未被拒" if not aborted else "")
    conn.close()
    # §D 链 v2：头部字段篡改检出
    _tamper_events(tmp)
    caught = False
    try:
        lg.Ledger.open(tmp)
    except lg.LedgerError:
        caught = True
    check("§D 链 v2 头部篡改检出", caught, "" if caught else "未检出")
    if host:
        hspec = {"kinds": os.path.join(AUD, host, "kinds.yml"),
                 "prereg": os.path.join(AUD, host, "prereg")}
        # S1：宿主域逻辑（检索/生命周期/决策三件）已平移至独立包 evocore——不再在宿主目录下
        dom = [os.path.join(AUD, "evocore", f"{m}.py") for m in ("retrieval", "lifecycle", "decision")]
        check("§B 宿主 kinds 注册", os.path.isfile(hspec["kinds"]))
        check("§B 宿主 prereg 判据", os.path.isdir(hspec["prereg"]))
        _check_prereg(hspec["prereg"], "§B 宿主",
                      os.path.join(AUD, "audit-kit", "core", "prereg.py"))
        check("§B 宿主域逻辑模块", all(os.path.isfile(p) for p in dom),
              "" if all(os.path.isfile(p) for p in dom) else f"缺 {[p for p in dom if not os.path.isfile(p)]}")

# ── §K 中库形态（S3/T4；对被测物只读） ──
_KB_NEED = ("kb.db", "kb.manifest.json", "gov", "evo", "kinds.yml", "prereg", "tools/kb.py")
_KB_KIND = re.compile(r"^\s{2}[A-Za-z_][A-Za-z0-9_]*:\s*$", re.M)


def _dir_hashes(root: str) -> dict:
    """目录内逐文件 sha256（排除 *.manifest.json 与 __pycache__）。"""
    out = {}
    for dp, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if d != "__pycache__"]
        for f in fs:
            if f.endswith(".manifest.json"):
                continue
            full = os.path.join(dp, f)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, root).replace("\\", "/")] = hashlib.sha256(fh.read()).hexdigest()
    return out


def _aggregate(files: dict) -> str:
    # 聚合公式与 build/assemble.py `_aggregate` 同源（路径\0sha 分行）——中库清单的
    # gov/evo 段即 S2 清单投影，公式必须逐字一致方能双向对账。
    body = "".join(f"{k}\0{v}\n" for k, v in sorted(files.items()))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _kb_structure(kb: str) -> None:
    for n in _KB_NEED:
        check(f"§K 结构：{n} 在位", os.path.exists(os.path.join(kb, n)))


def _anchor_of(db: str) -> dict:
    """只读读档：events 数 + 链头（锚点比对用）。"""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    row = conn.execute("SELECT self_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    conn.close()
    return {"events": n, "head": row[0] if row else "0" * 64}


def _kb_manifest(kb: str) -> dict | None:
    p = os.path.join(kb, "kb.manifest.json")
    if not os.path.isfile(p):
        check("§K 清单可读（JSON 解析）", False, "缺失")
        return None
    try:
        with open(p, encoding="utf-8") as f:
            man = json.load(f)
    except ValueError as e:
        check("§K 清单可读（JSON 解析）", False, str(e)[:80])
        return None
    check("§K 清单可读（JSON 解析）", man.get("kb_spec") == "KB-SPEC-v1",
          f"kb_spec={man.get('kb_spec')!r}（期望 KB-SPEC-v1）")
    for comp in ("gov", "evo"):
        seg = man.get(comp) or {}
        on_disk = _dir_hashes(os.path.join(kb, comp))
        check(f"§K {comp} 载荷逐件哈希==清单", on_disk == seg.get("files", {}),
              f"清单 {len(seg.get('files', {}))} 件 vs 磁盘 {len(on_disk)} 件")
        check(f"§K {comp} aggregate_sha==清单", _aggregate(on_disk) == seg.get("aggregate_sha", ""))
        inner = os.path.join(kb, comp, f"{comp}.manifest.json")
        if os.path.isfile(inner) and seg.get("manifest_sha16"):
            with open(inner, "rb") as fh:
                got = hashlib.sha256(fh.read()).hexdigest()[:16]
            check(f"§K {comp} 内嵌清单 sha==登记", got == seg["manifest_sha16"],
                  f"{got} != {seg['manifest_sha16']}")
    dbinfo = man.get("db") or {}
    dbp = os.path.join(kb, "kb.db")
    if os.path.isfile(dbp) and dbinfo.get("sha256"):
        with open(dbp, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        cur = _anchor_of(dbp)
        anchored = (cur["events"] == dbinfo.get("events") and cur["head"] == dbinfo.get("head"))
        if anchored:
            check("§K db sha==清单（在锚点处）", got == dbinfo["sha256"], "库被改动（或清单未同步）")
        else:
            # 锚点=建库/迁移基准；库生长后不再逐字节比对——明示 [N/A]（三态纪律：
            # "没检查"≠"检查通过"；篡改由 §K 链重放独立兜底）
            note(f"§K db 锚点比对（自锚点后已生长，现 {cur['events']} vs 锚 {dbinfo.get('events')} 事件）")
    return man


def _kb_chain_replay(kb: str) -> None:
    """链重放（库数据面）：只读读 SQLite，用 kb/gov 的哈希实现复算——不开写连接。"""
    db = os.path.join(kb, "kb.db")
    if not os.path.isfile(db):
        check("§K 链重放", False, "kb.db 缺失")
        return
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    miss = {"no_update", "no_delete"} - names
    check("§K 触发器在位", not miss, f"缺 {sorted(miss)}")
    carriers = [c for c in ("schema_version", "meta") if c in tables]
    check("§K schema 载体在位（双认）", bool(carriers), "meta/schema_version 均缺")
    hv = sys.modules.get("hashes")
    if hv is None:
        check("§K 链重放", False, "hashes 模块未载入（先跑治理核检查）")
        conn.close()
        return
    prev = hv.genesis_prev()
    broken, n = 0, 0
    for seq, actor, kind, row_prev, payload, self_h in conn.execute(
            "SELECT seq, actor, kind, prev_hash, payload, self_hash FROM events ORDER BY seq"):
        n += 1
        if row_prev != prev or hv.event_hash(prev, json.loads(payload), actor, kind) != self_h:
            broken += 1
            break
        prev = self_h
    conn.close()
    check(f"§K 链重放（{n} 事件·载体 {'/'.join(carriers) or '—'}）", broken == 0, "链断裂或哈希不符")


def _check_prereg(dirpath: str, label: str, loader_path: str) -> None:
    """S8-5①（20260923 开工批）：判据件**机械格式**检——版本行 + 生效日行，缺项即 FAIL。

    此前只检「目录非空」（`len(os.listdir(prereg)) >= 1`）：判据件有没有版本、能不能被决策
    留痕引用，一概不问 ⇒「有判据」与「有个空目录/一份没版本的草稿」在体检输出上**同形**。
    合格件的锚（`<名>@<版本>`，或件内自带 `判据锚：`）即决策留痕 `prereg` 字段的取值来源。
    `loader_path` 按形态取：宿主面用仓内治理核，中库面用**库自带的 gov 副本**
    （顺带验证副本里有这件检查器）。
    """
    if not os.path.isfile(loader_path):
        # 老库的 gov 副本早于 S8-5 ⇒ 检查器本身不在库里。这不是"判据缺失"，是**副本过旧**——
        # 报一条可机读的 FAIL 并给出升级路径（中库升级语义=换 gov/，库数据不动），
        # 绝不让体检抛 FileNotFoundError（崩在检查器加载上=仪器坏，不是被测物坏）。
        check(f"{label} 判据检查器在位（治理核副本含 core/prereg.py）", False,
              f"缺 {loader_path}——该库的 gov/evo 副本早于 S8-5，升级=换 gov/ 目录")
        return
    pr = _load(loader_path, "prereg_fmt")
    refs, problems = pr.scan_dir(dirpath)
    check(f"{label} 判据件可引用（≥1 份格式合格）", len(refs) >= 1,
          f"合格 {len(refs)} 份" + (f"；不合格 {[(n, m) for n, m in problems]}" if problems else ""))
    for name, miss in problems:
        check(f"{label} 判据件 {name} 机械格式（版本行+生效日行）", False, f"缺 {'/'.join(miss)}")
    if len(refs) > 1:
        print(f"  [注] {label} 有 {len(refs)} 份合格判据件；留痕指针取字典序首份（{refs[0][1]}）")


def _kb_host_three(kb: str) -> None:
    kinds = os.path.join(kb, "kinds.yml")
    if os.path.isfile(kinds):
        with open(kinds, encoding="utf-8") as f:
            text = f.read()
        check("§B(kb) kind 注册可解析（≥1 声明）", bool(_KB_KIND.search(text)))
    prereg = os.path.join(kb, "prereg")
    n = len(os.listdir(prereg)) if os.path.isdir(prereg) else 0
    check("§B(kb) prereg 判据位非空", n >= 1, f"目录内 {n} 件")
    _check_prereg(prereg, "§B(kb)", os.path.join(kb, "gov", "core", "prereg.py"))
    dom = [os.path.join(kb, "evo", "evocore", f"{m}.py")
           for m in ("retrieval", "lifecycle", "decision")]
    check("§B(kb) 域逻辑模块在位", all(os.path.isfile(p) for p in dom))


def check_kb(kb: str):
    """§K 中库形态：结构 → 清单自洽 → 治理核（§A/§D）→ 链重放 → §B 三件。"""
    kb = os.path.abspath(kb)
    _kb_structure(kb)
    _kb_manifest(kb)
    check_kernel_auditkit(None, os.path.join(kb, "gov"))     # §A/§D（复用重装形态检查）
    _kb_chain_replay(kb)
    _kb_host_three(kb)


def check_kernel_fused(path: str):
    src = open(path, encoding="utf-8").read()
    for sym in ("class Store", "def append", "def verify", "def rows",
                "no_update", "no_delete", "schema_version",
                "memory_append", "tombstone", "GENESIS"):
        check(f"§A(fused) 含 {sym}", sym in src)
    # 实跑：init→篡改→verify 检出
    tmp = os.path.join(tempfile.mkdtemp(), "f.db")
    py = [sys.executable, "-X", "utf8", path]
    subprocess.run(py + ["init", tmp, "--level", "G1"], cwd=AUD, check=True, capture_output=True)
    subprocess.run(py + ["append", tmp, "--id", "c1", "--content", "符合性样本", "--keywords", "样本"],
                   cwd=AUD, check=True, capture_output=True)
    r = subprocess.run(py + ["verify", tmp], cwd=AUD, capture_output=True, text=True)
    check("§D(fused) verify 通过", r.returncode == 0, r.stderr[-_ERR_SNIPPET:])
    _tamper_events(tmp)
    r2 = subprocess.run(py + ["verify", tmp], cwd=AUD, capture_output=True, text=True)
    check("§D(fused) 链 v2 头部篡改检出", r2.returncode != 0, r2.stderr.strip().splitlines()[-1][:80] if r2.returncode else "未检出")
    # §F 判别力测试（20260923 升级：字段在位=恒真锚，与 blender 线点名的 F-155 同族——
    # 改为"破坏框架段→哈希必变"的判别力断言：检查检查器）
    def _fsha(path):
        spec = importlib.util.spec_from_file_location("fsha_" + str(abs(hash(path))), path)
        mm = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mm
        spec.loader.exec_module(mm)
        return mm.framework_sha()
    s1 = _fsha(path)
    bp = os.path.join(tempfile.mkdtemp(), "broken.py")
    with open(bp, "w", encoding="utf-8", newline="\n") as _f:
        _f.write(src.replace("append-only: 禁 UPDATE", "X", 1))
    s2 = _fsha(bp)
    check("§F framework_sha 判别力（破坏必变）", s1 != s2, f"两侧同值 {s1}（判别力近零）")
    check("§F framework_sha 已输出", len(s1) == 16, repr(s1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", default=None,
                    help="重装形态内核根：'audit-kit'（原字面量）或任一产物目录（镜像树/平铺二布局）")
    ap.add_argument("--host", default=None, help="宿主目录名（如 memsys）")
    ap.add_argument("--fused", default=None, help="融合形态：单文件路径")
    ap.add_argument("--kb", default=None, help="中库形态：kb/ 目录（S3/T4 §K 六查）")
    a = ap.parse_args()
    if a.kernel:                                   # 次序与原版一致：--kernel 优先于 --fused
        check_kernel_auditkit(a.host, a.kernel)
    elif a.kb:
        check_kb(a.kb)
    elif a.fused:
        p = a.fused if os.path.isabs(a.fused) else os.path.join(AUD, a.fused)
        check_kernel_fused(p)
    else:
        ap.print_help(); sys.exit(2)
    fails = [r for r in RESULTS if r[1] is False]
    na = [r for r in RESULTS if r[1] is None]
    for name, ok, ev in RESULTS:
        state = "PASS" if ok else ("FAIL" if ok is False else "N/A")
        print(f"  [{state}] {name}" + (f"  {ev}" if ev and ok is False else ""))
    passed = len(RESULTS) - len(fails) - len(na)
    extra = f"（其中 N/A {len(na)} 项——未检查，非通过）" if na else ""
    print(f"conformance: {passed}/{len(RESULTS)} PASS{extra}")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":     # S3/T4：守卫化（可被测试 exec 载入做公式同步对拍；CLI 行为不变）
    main()
