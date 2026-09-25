#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo_e2e.py — S5 端到端演示（五段 · 《S5设计-端到端演示全量落地架构》§2.1）

段0 共享样本（4 条目，固定 created_at，全部 procedural=零衰减 ⇒ 榜单跨形态可比）
段1 微内核（L1 融合）：init → import → retrieve → selftest → verify（framework_sha 打印）
段2 中库（L1.5 包内）：make_kb init → import → query → verify → conformance --kb（体检）
段3 共库（L2 服务）：server init → **两个独立客户端（HTTP）各写 2 条**并读 → memory_verify
段4 **升格直迁**：段2 的 kb/kb.db → 服务 libs/<name>.db（拷贝语义）+ 三同判据 + MCP 复核
段5 **跨形态一致性对照**：同一查询三入口排名逐项；差异必须为空或**挂已登记 D 号**（D1 如实展示）

产物：`build/out/demo/REPORT.md` + `demo.json`；任一段断言失败 → 非零退出（fail-closed）。
用法: py -X utf8 build/demo_e2e.py [--root build/out/demo]
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEAT = os.path.join(ROOT, "evo-seat", "evo_seat.py")
MK = os.path.join(ROOT, "build", "make_kb.py")
CONF = os.path.join(ROOT, "audit-kit", "conformance.py")
TESTS = os.path.join(ROOT, "build", "tests")
sys.path.insert(0, TESTS)
from mcp_client import MCPClient  # noqa: E402

SAMPLE_CREATED = "2026-08-01T00:00:00"          # 固定时间原点（procedural ⇒ 零衰减，榜单不受 age 影响）
QUERY = "玻璃 材质"
_SAMPLE = [
    {"id": "e1", "content": "玻璃材质 IOR 1.45 透射 1.0", "keywords": ["玻璃", "材质"],
     "type": "procedural", "importance": 8},
    {"id": "e2", "content": "三点布光 主光 45 度 辅光 2:1", "keywords": ["布光", "灯光"],
     "type": "procedural", "importance": 7},
    {"id": "e3", "content": "材质基材 先建基材再派生", "keywords": ["材质", "基材"],
     "type": "procedural", "importance": 6},
    {"id": "e4", "content": "渲染爆光 降档收敛", "keywords": ["渲染", "曝光"],
     "type": "procedural", "importance": 4},
]
R = {"segments": {}, "comparison": {"query": QUERY, "rows": [], "diffs": []},
     "t1_defects": {}, "readings": {}}


def _run(argv, **kw):
    r = subprocess.run([sys.executable, "-X", "utf8", *argv], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", **kw)
    if r.returncode != 0:
        raise SystemExit(f"命令失败（{argv[0]} …）：\n{r.stdout}")
    return r.stdout


def _rel(p):
    """仓内→相对；仓外（临时目录，Windows 跨盘符）→原样（仅用于显示）。"""
    try:
        return os.path.relpath(p, ROOT)
    except ValueError:
        return p


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _digest(db):
    """只读读档：events 数 / 链头 / 全链摘要（升格三同判据用）。"""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = list(conn.execute("SELECT seq,actor,kind,payload,prev_hash,self_hash FROM events ORDER BY seq"))
    conn.close()
    body = "".join("\t".join(str(x) for x in r) + "\n" for r in rows)
    return {"events": len(rows), "head": rows[-1][5] if rows else "0" * 64,
            "digest": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]}


def _jsonl(path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for e in _SAMPLE:
            f.write(json.dumps({**e, "created_at": SAMPLE_CREATED}, ensure_ascii=False) + "\n")
    return path


def seg1_fused(root):
    """段1 微内核：自检 + 导入 + 检索 + 链验证。"""
    d = os.path.join(root, "fused")
    os.makedirs(d, exist_ok=True)
    lib = os.path.join(d, "kb.db")
    _run([SEAT, "init", lib, "--level", "G1"])
    _run([SEAT, "import", lib, _jsonl(os.path.join(d, "sample.jsonl"))])
    out = _run([SEAT, "retrieve", lib, QUERY, "-k", "3", "--at", "2026-09-23T12:00:00"])
    rank = [ln.split()[1] for ln in out.strip().splitlines() if ln.strip()]
    st = _run([SEAT, "selftest"])
    vf = _run([SEAT, "verify", lib])
    sha = [ln for ln in vf.splitlines() if "framework_sha" in ln]
    R["segments"]["seg1_fused"] = {"retrieve": rank, "selftest": st.strip().splitlines()[-1],
                                   "verify": sha[0].strip() if sha else vf.strip()}
    return rank


def seg2_kb(root):
    """段2 中库：建库 + 导入 + 检索 + 体检。"""
    kb = os.path.join(root, "kb")
    if os.path.isdir(kb):
        shutil.rmtree(kb)
    _run([MK, "init", kb])
    imp = _run([os.path.join(kb, "tools", "kb.py"), "import", kb, _jsonl(os.path.join(root, "sample.jsonl"))])
    q = _run([os.path.join(kb, "tools", "kb.py"), "query", kb, QUERY, "-k", "3"])
    rank = [ln.split()[1] for ln in q.strip().splitlines() if ln.strip() and ln.strip()[0].isdigit()]
    chk = _run([CONF, "--kb", kb])
    line = [ln for ln in chk.splitlines() if ln.startswith("conformance:")]
    R["segments"]["seg2_kb"] = {"import": imp.strip(), "query": rank, "check": line[0] if line else "?"}
    return rank, os.path.join(kb, "kb.db")


def _http_post(port, payload, grant=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"X-L2-Grant": grant} if grant else {})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


CLIENT_CODE = """import json, sys, urllib.request
port, tag, ids = int(sys.argv[1]), sys.argv[2], sys.argv[3].split(",")
grant = {"alpha": "g1", "beta": "g2"}[tag]          # B′：接入键随客户端（发卡即定身份）
for i in ids:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "memory_append",
                                  "arguments": {"lib": "shared.db", "id": i,
                                                "content": tag + " 写入样本 " + i,
                                                "keywords": ["共库", tag],
                                                "type": "procedural", "importance": 5}}}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:%d/mcp" % port, data=body,
                                 headers={"X-L2-Grant": grant})
    r = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
    if r["result"]["isError"]:
        print(r["result"]["content"][0]["text"]); sys.exit(1)
print("client ok:", tag)
"""


def seg3_server(root):
    """段3 共库：两个独立客户端（HTTP）并写同一 server。"""
    srv = os.path.join(ROOT, "build", "out", "server")
    d = os.path.join(root, "l2")
    if os.path.isdir(d):
        shutil.rmtree(d)
    shutil.copytree(srv, d, ignore=shutil.ignore_patterns("__pycache__", "calls.jsonl", "caps.json"))
    libs = os.path.join(d, "libs")
    _run([os.path.join(d, "server.py"), "init", "--libs-root", libs, "--lib", "shared.db", "--grant-id", "g1"])
    _run([os.path.join(d, "server.py"), "grant", "--libs-root", libs,
          "--grant-id", "g2", "--actor-prefix", "llm:local"])   # B′：beta 客户端的第二张卡
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    proc = subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(d, "server.py"),
                             "--libs-root", libs, "--http", f":{port}"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(40):                        # 等端口就绪
            try:
                _http_post(port, {"jsonrpc": "2.0", "id": 0, "method": "ping"})
                break
            except OSError:
                time.sleep(0.25)
        def _spawn(tag, ids):
            return subprocess.Popen([sys.executable, "-X", "utf8", "-c", CLIENT_CODE,
                                     str(port), tag, ids],
                                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1 = _spawn("alpha", "a1,a2")
        p2 = _spawn("beta", "b1,b2")
        for p in (p1, p2):
            out, err = p.communicate(timeout=60)
            if p.returncode != 0:
                raise SystemExit(f"客户端失败：{out.decode()} {err.decode()}")
        vf = _http_post(port, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "memory_verify", "arguments": {"lib": "shared.db"}}},
                        grant="g1")
        verify = json.loads(vf["result"]["content"][0]["text"])
        con = sqlite3.connect(os.path.join(libs, "shared.db"))
        ids = sorted(r[0] for r in con.execute(
            "SELECT json_extract(payload,'$.entry_id') FROM events WHERE kind='entry_append'"))
        actors = sorted({r[0] for r in con.execute("SELECT actor FROM events WHERE kind='entry_append'")})
        con.close()
        wrote = {"alpha": ["a1", "a2"], "beta": ["b1", "b2"]}
        ok = verify.get("ok") and ids == sorted(sum(wrote.values(), []))
        R["segments"]["seg3_server"] = {"clients": wrote, "entries_in_ledger": ids, "actors": actors,
                                        "verify": verify, "ok": bool(ok)}
        if not ok:
            raise SystemExit(f"段3 断言失败：verify={verify} ids={ids}")
        return os.path.join(libs, "shared.db")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def seg4_promote(root, kb_db):
    """段4 升格直迁：中库 kb.db → 服务 libs/promoted.db（拷贝语义+三同判据+MCP 复核）。"""
    libs = os.path.join(root, "l2", "libs")
    dst = os.path.join(libs, "promoted.db")
    before, before_sha = _digest(kb_db), _sha(kb_db)
    shutil.copyfile(kb_db, dst)
    after, after_sha = _digest(dst), _sha(dst)
    three = (before == after and before_sha == after_sha)
    c = MCPClient([sys.executable, "-X", "utf8", os.path.join(root, "l2", "server.py"),
                   "--libs-root", libs], env={**os.environ, "L2_GRANT": "g1"})
    try:
        c.request("initialize", {"protocolVersion": "2025-06-18"})
        ok_v, v, _ = c.call_tool("memory_verify", {"lib": "promoted.db"})
        ok_r, hits, _ = c.call_tool("memory_retrieve", {"lib": "promoted.db", "query": QUERY, "k": 3})
    finally:
        c.close()
    rank = [h["id"] for h in hits.get("hits", [])] if ok_r else []
    R["segments"]["seg4_promote"] = {"three_same": {"pass": bool(three), "events": after["events"],
                                                   "head": after["head"][:16],
                                                   "digest": after["digest"],
                                                   "db_sha_equal": before_sha == after_sha},
                                     "mcp_verify": v, "mcp_retrieve": rank}
    if not (three and ok_v and v.get("ok")):
        raise SystemExit(f"段4 断言失败：three={three} verify={v}")
    return rank


def seg5_compare(fused_rank, kb_rank, l2_rank):
    """段5 跨形态一致性对照（差异必须为空或挂 D 号）。"""
    rows = [{"entry": "fused(微内核)", "rank": fused_rank},
            {"entry": "kb(中库)", "rank": kb_rank},
            {"entry": "l2(共库·升格后)", "rank": l2_rank}]
    diffs = []
    base = fused_rank
    for r in rows[1:]:
        if r["rank"] != base:
            diffs.append({"vs": r["entry"], "base": base, "got": r["rank"], "registered": None})
    R["comparison"]["rows"] = rows
    R["comparison"]["diffs"] = diffs
    return rows, diffs


def seg0_t1_probes(root, kb_db):
    """T1 缺陷反转探针：① kb 投影含 created_at ② 融合件墓碑生效（副本上跑，不动段1库）。"""
    sys.path.insert(0, ROOT)
    from evocore import project_entries
    sys.path[:0] = [os.path.join(root, "kb", "gov", "core"), os.path.join(root, "kb", "gov", "ledger")]
    import importlib.util
    s = importlib.util.spec_from_file_location("led_kb", os.path.join(root, "kb", "gov", "ledger", "ledger.py"))
    m = importlib.util.module_from_spec(s)
    sys.modules["led_kb"] = m
    s.loader.exec_module(m)
    led = m.Ledger.open(kb_db)
    proj = project_entries(led.rows())
    led.close()
    has_ts = [e.get("created_at") for e in proj.values() if e.get("created_at")]
    d = os.path.join(root, "fused_tomb")
    os.makedirs(d, exist_ok=True)
    lib = os.path.join(d, "t.db")
    _run([SEAT, "init", lib, "--level", "G1"])
    _run([SEAT, "append", lib, "--id", "t1", "--content", "待墓碑", "--keywords", "墓碑", "--importance", "9"])
    _run([SEAT, "tombstone", lib, "t1"])
    out = _run([SEAT, "retrieve", lib, "墓碑"]).strip()
    R["t1_defects"] = {"kb_projection_has_created_at": bool(has_ts),
                       "created_at_sample": has_ts[0] if has_ts else None,
                       "fused_tombstone_exits": (out == "")}
    if not (has_ts and out == ""):
        raise SystemExit(f"T1 探针未反转：{R['t1_defects']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(ROOT, "build", "out", "demo"))
    a = ap.parse_args()
    if os.path.isdir(a.root):
        shutil.rmtree(a.root)
    os.makedirs(a.root)
    t0 = time.perf_counter()
    print("段1 微内核（L1 融合）…")
    fused_rank = seg1_fused(a.root)
    print("段2 中库（L1.5 包内）…")
    kb_rank, kb_db = seg2_kb(a.root)
    print("段0 T1 缺陷反转探针…")
    seg0_t1_probes(a.root, kb_db)
    print("段3 共库（L2 服务·双客户端并写）…")
    shared_db = seg3_server(a.root)
    print("段4 升格直迁（中库→共库）…")
    l2_rank = seg4_promote(a.root, kb_db)
    print("段5 跨形态一致性对照…")
    rows, diffs = seg5_compare(fused_rank, kb_rank, l2_rank)
    R["readings"]["elapsed_s"] = round(time.perf_counter() - t0, 2)
    R["readings"]["shared_db"] = _rel(shared_db)

    lines = ["# S5 端到端演示报告（`build/demo_e2e.py` 产出）", "",
             f"- 共享样本：{len(_SAMPLE)} 条目（created_at={SAMPLE_CREATED}；全 procedural=零衰减）；查询=`{QUERY}`",
             f"- 总耗时：{R['readings']['elapsed_s']} s", "", "## 五段读数", ""]
    for k, v in R["segments"].items():
        lines.append(f"- **{k}**：`{json.dumps(v, ensure_ascii=False)}`")
    lines += ["", "## 跨形态一致性对照（段5）", "",
              "| 形态 | 排名 |", "|---|---|"]
    for r in rows:
        lines.append(f"| {r['entry']} | {r['rank']} |")
    lines += ["", f"- 差异：**{len(diffs)} 项**" + ("（零差异）" if not diffs else f"：{json.dumps(diffs, ensure_ascii=False)}"),
              "- D1（bad-ts 跨形态分歧）保持登记、如实展示：见 `evocore/README` D 表（本演示样本不含 bad-ts 路径）",
              "", "## T1 缺陷反转探针", "",
              f"- kb 投影含 created_at：**{R['t1_defects']['kb_projection_has_created_at']}**（样本 {R['t1_defects']['created_at_sample']}）",
              f"- 融合件墓碑后检索为空：**{R['t1_defects']['fused_tombstone_exits']}**"]
    with open(os.path.join(a.root, "REPORT.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(a.root, "demo.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(R, f, ensure_ascii=False, sort_keys=True, indent=2)
    print(f"\n演示完成：{R['readings']['elapsed_s']}s；跨形态差异 {len(diffs)} 项；报告 {_rel(a.root)}/REPORT.md")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
