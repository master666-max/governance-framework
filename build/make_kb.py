# -*- coding: utf-8 -*-
"""make_kb.py — 中库构建器（S3/T3：《S3设计-中库规范件全量落地架构》§2.5）

职责：把 **S2 产物**（`build/out/vendored/{gov,evo}`）+ **模板**（`build/kb_template/`）落成
一个真中库 `kb/`，或把既有库（融合件/任意同 schema 库）**迁移**为中库。

命令：
  init    <kb_dir>            起空库（gov 建 kb.db）并落位载荷+模板+清单
  migrate <lib.db> <kb_dir>   迁移（**拷贝语义**：db 零写入；三同判据=events/全链摘要/链头）
  check   <kb_dir>            体检：conformance --kb（子进程）+ 与 S2 登记件的双向对账
  audit   <kb_dir>            观测：操作计时 + 复用记账（模板件/副本/生成件）

纪律（照设计件）：①**迁移动作对 db 字节中立**（sha 前后相同）②三同判据全过才报成功
③schema 载体差异（E4：首次 gov 开库补建 schema_version 表）**强制申报**进清单
reconciliation 段——不许静默 ④检查器（conformance）对被测物只读，本件不对既有库写一字。
确定性：清单无时间戳；载荷/模板=逐字节副本。
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDORED = os.path.join(ROOT, "build", "out", "vendored")
MANS = os.path.join(ROOT, "build", "manifests")
TEMPLATE = os.path.join(ROOT, "build", "kb_template")
CONF = os.path.join(ROOT, "audit-kit", "conformance.py")
GENESIS = "0" * 64
MACHINE_STEPS = ("gov", "evo")
_IGNORE = shutil.ignore_patterns("__pycache__")   # 落位复制统一忽略表
_MS_PER_S = 1000                                  # 秒→毫秒（观测输出换算）


def sha_f(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _digest(files):
    body = "".join(f"{k}\0{v}\n" for k, v in sorted(files.items()))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def chain_digest(db):
    """只读读档：events 数 / 链头 / 全链摘要（seq·actor·kind·payload·prev·self 逐行）。"""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = list(conn.execute(
        "SELECT seq, actor, kind, payload, prev_hash, self_hash FROM events ORDER BY seq"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    body = "".join("\t".join(str(x) for x in r) + "\n" for r in rows)
    return {"events": len(rows), "head": rows[-1][5] if rows else GENESIS,
            "digest": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            "carrier": [c for c in ("schema_version", "meta") if c in tables]}


def _require_payloads():
    need = [os.path.join(VENDORED, c, f"{c}.manifest.json") for c in MACHINE_STEPS]
    miss = [p for p in need if not os.path.isfile(p)]
    if miss:
        raise SystemExit(f"S2 产物缺失：{miss}\n先跑 py -X utf8 build/assemble.py all")
    return {c: json.load(open(os.path.join(VENDORED, c, f"{c}.manifest.json"), encoding="utf-8"))
            for c in MACHINE_STEPS}


def _place_payloads(kb, src_man):
    rep = {}
    for comp in MACHINE_STEPS:
        shutil.copytree(os.path.join(VENDORED, comp), os.path.join(kb, comp), ignore=_IGNORE)
        rep[comp] = {"version": src_man[comp]["versions"],
                     "aggregate_sha": src_man[comp]["aggregate_sha"],
                     "files": src_man[comp]["files"],
                     "manifest_sha16": sha_f(os.path.join(kb, comp, f"{comp}.manifest.json"))[:16]}
    return rep


def _place_template(kb):
    for rel in ("kinds.yml", "README.md"):
        shutil.copyfile(os.path.join(TEMPLATE, rel), os.path.join(kb, rel))
    for sub in ("prereg", "index", "tools"):
        shutil.copytree(os.path.join(TEMPLATE, sub), os.path.join(kb, sub), ignore=_IGNORE)


def _payload_ready(kb):
    """取 S2 产物并落位（返回 gov/evo 登记段）——init/migrate 共用前序。"""
    return _place_all(kb, _require_payloads())


def _place_all(kb, payload):
    """落位载荷+模板（init/migrate 共用）→ 返回 gov/evo 登记段。"""
    placed = _place_payloads(kb, payload)
    _place_template(kb)
    return placed


def _created_by():
    return {"tool": "build/make_kb.py", "tool_sha16": sha_f(os.path.abspath(__file__))[:16],
            "kb_cli": "tools/kb.py"}


def _write_manifest(kb, payload, dbinfo, recon):
    man = {"kb_spec": "KB-SPEC-v1", "kb_spec_version": "1.0.0", "created_by": _created_by(),
           "gov": payload["gov"], "evo": payload["evo"], "db": dbinfo, "reconciliation": recon}
    body = json.dumps(man, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with open(os.path.join(kb, "kb.manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(body)


def _make_empty_db(kb):
    """用 kb/gov 建空库（唯一会写 db 的时刻；迁移路径不做此事）。"""
    sys.path[:0] = [os.path.join(kb, "gov", "core"), os.path.join(kb, "gov", "ledger")]
    import importlib.util
    spec = importlib.util.spec_from_file_location("led_kb", os.path.join(kb, "gov", "ledger", "ledger.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["led_kb"] = mod
    spec.loader.exec_module(mod)
    led = mod.Ledger.open(os.path.join(kb, "kb.db"))
    n = led.count()
    led.close()
    return n


def _require_empty_target(kb):
    if os.path.isdir(kb) and os.listdir(kb):
        raise SystemExit(f"目标目录非空（拒绝覆盖）：{kb}")
    os.makedirs(kb, exist_ok=True)


def cmd_init(a):
    t0 = time.perf_counter()
    _require_empty_target(a.kb)
    placed = _payload_ready(a.kb)
    n = _make_empty_db(a.kb)
    info = chain_digest(os.path.join(a.kb, "kb.db"))
    dbinfo = {"file": "kb.db", "sha256": sha_f(os.path.join(a.kb, "kb.db")),
              "events": info["events"], "head": info["head"], "schema_carrier": "/".join(info["carrier"])}
    _write_manifest(a.kb, placed, dbinfo, [])
    print(f"init: {a.kb}（events={n} 载体={'/'.join(info['carrier'])} "
          f"gov={placed['gov']['version']} evo={placed['evo']['version']}）"
          f" 耗时 {time.perf_counter()-t0:.2f}s")


def cmd_migrate(a):
    t0 = time.perf_counter()
    if not os.path.isfile(a.lib):
        raise SystemExit(f"源库不存在：{a.lib}")
    _require_empty_target(a.kb)
    before = chain_digest(a.lib)
    before_sha = sha_f(a.lib)
    shutil.copyfile(a.lib, os.path.join(a.kb, "kb.db"))
    placed = _payload_ready(a.kb)
    after = chain_digest(os.path.join(a.kb, "kb.db"))
    after_sha = sha_f(os.path.join(a.kb, "kb.db"))
    ok_three = (before["events"] == after["events"] and before["head"] == after["head"]
                and before["digest"] == after["digest"])
    ok_bytes = before_sha == after_sha
    recon = []
    if after["carrier"] == ["meta"]:
        recon.append({"what": "首次 gov 开库补建 schema_version 表（schema 载体对账）",
                      "at": "migrate", "declared": True,
                      "note": "不触碰 events 数据；三同判据为证"})
    dbinfo = {"file": "kb.db", "sha256": after_sha, "events": after["events"],
              "head": after["head"], "schema_carrier": "/".join(after["carrier"])}
    _write_manifest(a.kb, placed, dbinfo, recon)
    print(f"migrate: {a.lib} → {a.kb}（{time.perf_counter()-t0:.2f}s）")
    print(f"  三同判据：events {before['events']}=={after['events']} · 链头 {'同' if before['head']==after['head'] else '异'}"
          f" · 全链摘要 {before['digest']}=={after['digest']} ⇒ {'PASS' if ok_three else 'FAIL'}")
    print(f"  迁移字节中立：db sha {before_sha[:16]}=={after_sha[:16]} ⇒ {'PASS' if ok_bytes else 'FAIL'}")
    print(f"  载体申报：{'/'.join(after['carrier'])}"
          + ("（已声明 schema 对账：首次 gov 开库补建 schema_version 表）" if recon else "（无需对账声明）"))
    if not (ok_three and ok_bytes):
        raise SystemExit("migrate 判据未过——已停止（目标目录保留供审）")


def cmd_check(a):
    r = subprocess.run([sys.executable, "-X", "utf8", CONF, "--kb", a.kb],
                       capture_output=True, text=True, encoding="utf-8")
    print(r.stdout.rstrip())
    if r.returncode != 0:
        print(r.stderr.rstrip())
        return 1
    man = json.load(open(os.path.join(a.kb, "kb.manifest.json"), encoding="utf-8"))
    for comp in MACHINE_STEPS:
        reg = os.path.join(MANS, f"{comp}.manifest.json")
        if os.path.isfile(reg):
            rman = json.load(open(reg, encoding="utf-8"))
            same = (man[comp]["aggregate_sha"] == rman["aggregate_sha"]
                    and man[comp]["files"] == rman["files"])
            print(f"  [{'同' if same else '异'}] {comp} 与 S2 登记件对账（aggregate+逐件）")
    return 0


def cmd_audit(a):
    kb = a.kb
    if not os.path.isdir(kb):
        raise SystemExit(f"目录不存在：{kb}")
    t0 = time.perf_counter()
    info = chain_digest(os.path.join(kb, "kb.db"))
    t_read = time.perf_counter() - t0
    tmpl = []
    for dp, _ds, fs in os.walk(TEMPLATE):
        tmpl += [os.path.join(dp, f) for f in fs if not f.endswith(".pyc")]
    man = json.load(open(os.path.join(kb, "kb.manifest.json"), encoding="utf-8"))
    copies = sum(len(man[c]["files"]) for c in MACHINE_STEPS)     # 载荷副本计数（读清单，不再走目录）
    gen = 1 + len(tmpl)          # kb.manifest.json + 模板件
    print(f"audit: {kb}")
    print(f"  操作计时（G6 观测位）：只读读档 {_MS_PER_S*t_read:.1f} ms")
    print(f"  复用记账（G7）：载荷副本 {copies} 件 · 生成/模板 {gen} 件（模板 {len(tmpl)} + 清单 1）")
    print(f"  库锚：events={info['events']} head={info['head'][:16]}… 载体={'/'.join(info['carrier'])}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="中库构建器（中库规范件 v1）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("kb")
    p = sub.add_parser("migrate")
    p.add_argument("lib")
    p.add_argument("kb")
    for name in ("check", "audit"):
        p = sub.add_parser(name)
        p.add_argument("kb")
    a = ap.parse_args()
    if a.cmd == "init":
        return cmd_init(a) or 0
    if a.cmd == "migrate":
        return cmd_migrate(a) or 0
    if a.cmd == "check":
        return cmd_check(a)
    return cmd_audit(a)


if __name__ == "__main__":
    sys.exit(main())
