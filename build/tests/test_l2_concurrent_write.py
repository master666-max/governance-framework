# -*- coding: utf-8 -*-
"""test_l2_concurrent_write.py — L2-1 多客户端并写**实测**（20260924 开工批 W5）

对应《设计-多Agent宿主共库-L2等级》§六 L2-1 的门：「双客户端并写 + 链完整 + 来源可查」。
本件不做演示，做**测量**：三条实测臂 + 两处判别力对照。

三条臂（各测一种"并发"，因为它们的失效模式不同）：
  A **同一服务件进程、两个 HTTP 客户端**并发写 —— 测 accept 循环的串行化：
    断言"两边都成功且链仍是一条、seq 不重不漏"；
  B **两个服务件进程**写同一个库 —— 测跨进程的单写者纪律：
    断言"接受数 + 拒绝数 = 尝试数，且链完整"——**绝不允许两边都自称成功而链分叉**；
  C **来源可查**的实读 —— 跑完 A 之后读 `sources`，把**看到的**如实钉住。

臂 C 是本件的主要产出：**B′ 已落地（L2-2·R4-a）**——接入键随传输层（HTTP 头 X-L2-Grant /
stdio 环境变量 L2_GRANT），归属由**帽**决定、不由客户端自报；两客户端两张卡 ⇒ 账上两个
actor（test_C 正向）＋ 无键/错键必拒（test_C2 负向）。W5a 时代的"全归一个 actor"现状钉桩
已被本版改写（预注册 P2 承诺）。

用法: py -X utf8 build/tests/test_l2_concurrent_write.py
"""
import json
import os
import shutil
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRV_OUT = os.path.join(ROOT, "build", "out", "server")
PY = [sys.executable, "-X", "utf8"]
_REFUSE_SNIP = 120        # 拒因原文截断长（只进断言消息，不参与判定）
N_CLIENT = 2                 # 客户端数
N_WRITE = 8                  # 每客户端写入条数
_PROC_WAIT = 25.0            # 服务件就绪上限（秒）
_LOG_SNIP = 400            # 断言消息里的输出截断长


def _run(args, cwd=None):
    r = subprocess.run([*PY, *args], capture_output=True, text=True,
                       encoding="utf-8", cwd=cwd)
    return r.returncode, r.stdout + r.stderr


def _deploy():
    if not os.path.isdir(SRV_OUT):
        raise AssertionError(f"装配产物缺失：{SRV_OUT}——先跑 `py -X utf8 build/assemble.py all`")
    d = tempfile.mkdtemp(prefix="l2cw_")
    srv = os.path.join(d, "server")
    shutil.copytree(SRV_OUT, srv, ignore=shutil.ignore_patterns("__pycache__", "calls.jsonl",
                                                                "caps.json", "libs"))
    os.makedirs(os.path.join(srv, "libs"), exist_ok=True)
    return d, srv


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Http:
    """起一个 HTTP 服务件、等它真能应答、拿到已 initialize 的客户端；用完必收。

    三处用例原先各抄一份"起进程/等就绪/terminate"（抄本会走偏，最坏的一种偏是忘 terminate
    ⇒ 留下孤儿进程占着库文件，下一个用例就以"库被外部写者占用"的名义莫名失败）。
    """

    def __init__(self, server_py, libs, tag, grant=None):
        self.server_py, self.libs, self.tag, self.grant = server_py, libs, tag, grant
        self.proc = None
        self.port = _free_port()

    def __enter__(self):
        self.proc = subprocess.Popen([*PY, self.server_py, "--http", f":{self.port}",
                                      "--libs-root", self.libs],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8")
        _wait_ready(self.port, self.proc)
        rpc = _Rpc(self.port, grant=self.grant)
        rpc.request("initialize", {"protocolVersion": "2025-06-18",
                                   "clientInfo": {"name": self.tag}})
        return rpc

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=20)
        return False


class _Rpc:
    """最小 JSON-RPC over HTTP 客户端（本服务件 HTTP 面=POST 绑定，无流式）。"""

    def __init__(self, port, grant=None):
        self.url = f"http://127.0.0.1:{port}/"
        self.id = 0
        self.grant = grant

    def request(self, method, params=None):
        self.id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self.id, "method": method,
                           "params": params or {}}, ensure_ascii=False).encode("utf-8")
        hdr = {"Content-Type": "application/json"}
        if self.grant:
            hdr["X-L2-Grant"] = self.grant              # B′：接入键随传输层，不进协议载荷
        req = urllib.request.Request(self.url, data=body, headers=hdr)
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "replace").strip()
        if not raw:                                          # 通知类：202 空体
            return {}
        msg = json.loads(raw)
        if "error" in msg:
            raise RuntimeError(f"JSON-RPC error {msg['error'].get('code')}: "
                               f"{msg['error'].get('message')}")
        return msg.get("result", {})


def _wait_ready(port, proc):
    """轮询到服务件真能应答为止；超时=如实失败（不 sleep 固定时长，也不当"没测"放过）。"""
    deadline = time.time() + _PROC_WAIT
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"服务件提前退出 rc={proc.returncode}")
        try:
            _Rpc(port).request("initialize", {"protocolVersion": "2025-06-18",
                                              "clientInfo": {"name": "probe"}})
            return
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            last = f"{type(e).__name__}:{e}"
            time.sleep(0.1)
    raise AssertionError(f"服务件 {_PROC_WAIT}s 内未就绪：{last}")


def _append(rpc, lib, eid, content):
    """tools/call memory_append → (status, 原文)；status ∈ {appended, deduped, refused}。

    三态必须分开数：`deduped` 是"成功但**不**进链"（内容级去重）。把它算进"接受数"
    再去对链增量，就会做出"丢了写"的假指控——本件一开始正是这样错的。
    服务件把工具级拒绝放在 result 里（非 JSON-RPC error），故按文本分派。
    """
    r = rpc.request("tools/call", {"name": "memory_append",
                                   "arguments": {"lib": lib, "id": eid, "content": content,
                                                 "keywords": ["并写"], "type": "procedural",
                                                 "importance": 5}})
    txt = json.dumps(r, ensure_ascii=False)
    if r.get("isError") or "REFUSE:" in txt or "DENY:" in txt:
        return "refused", txt
    return ("deduped", txt) if '"deduped"' in txt.replace(chr(92), "") else ("appended", txt)


_ACTOR_LINE = re.compile(r"^\s+(\S+)\s+\d+ 条 ·", re.M)


# 复算用的治理核从**源码树**取（路径稳定）。曾从各测试的临时部署目录取：模块会被
# 缓存，第二个用例拿到的是**上一个已被 tearDown 删掉的目录**里的 ledger 模块，
# 报出 "schema.sql 缺失" 这种与真相无关的错——读侧独立复算不必跟着部署走。
sys.path.insert(0, os.path.join(ROOT, "audit-kit", "ledger"))
sys.path.insert(0, os.path.join(ROOT, "audit-kit", "core"))
from ledger import Ledger                           # noqa: E402


def _verify_ledger(srv, lib):
    """独立复算链（不走被测服务件自己的嘴）。→ (事件数, seq 列表)。开库即验：坏链在此抛错。"""
    led = Ledger.open(os.path.join(srv, "libs", lib))
    seqs = [row[0] for row in led.rows()]
    led.close()
    return len(seqs), seqs


def _events(srv, lib="shared.db"):
    """链上事件数（独立复算）。init 自带一条 capability_issue ⇒ 一切断言按**增量**算。"""
    return _verify_ledger(srv, lib)[0]


def _writers(sources_out, kind="entry_append"):
    """→ {actor: 该 actor 名下某 kind 的条数}：从 sources 的 `kind=N` 明细行反推归属。"""
    out = {}
    lines = sources_out.splitlines()
    for i, ln in enumerate(lines):
        m = _ACTOR_LINE.match(ln)
        if not m or i + 1 >= len(lines):
            continue
        det = lines[i + 1]
        dm = re.search(rf"{kind}=(\d+)", det)
        if dm:
            out[m.group(1)] = int(dm.group(1))
    return out


def _actors(sources_out):
    """`ops sources` 读数里的 actor 集合（每库一段 + 全域一段，故取去重）。"""
    return {m.group(1) for m in _ACTOR_LINE.finditer(sources_out)}


class TestL2ConcurrentWrite(unittest.TestCase):
    def setUp(self):
        self.tmp, self.srv = _deploy()
        self.libs = os.path.join(self.srv, "libs")
        self.server_py = os.path.join(self.srv, "server.py")
        rc, out = _run([self.server_py, "init", "--libs-root", self.libs, "--lib", "shared.db"])
        self.assertEqual(rc, 0, out[-_LOG_SNIP:])
        rc, out = _run([self.server_py, "grant", "--libs-root", self.libs,
                        "--grant-id", "g2", "--actor-prefix", "llm:local"])
        self.assertEqual(rc, 0, out[-_LOG_SNIP:])       # B′：第二客户端的第二张卡

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 臂 A：同一进程、两客户端并发 ────────────────────────────────────
    def _two_http_clients(self):
        port = _free_port()
        proc = subprocess.Popen([*PY, self.server_py, "--http", f":{port}",
                                 "--libs-root", self.libs],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8")
        results = {}
        try:
            _wait_ready(port, proc)
            def worker(tag, grant):
                rpc = _Rpc(port, grant=grant)
                rpc.request("initialize", {"protocolVersion": "2025-06-18",
                                           "clientInfo": {"name": tag}})
                tally = {"appended": 0, "deduped": 0, "refused": []}
                for i in range(N_WRITE):
                    st, txt = _append(rpc, "shared.db", f"{tag}-{i}", f"{tag} 第 {i} 条")
                    if st == "refused":
                        tally["refused"].append(txt[:_REFUSE_SNIP])
                    else:
                        tally[st] += 1
                results[tag] = tally
            cards = [(f"c{k}", f"g{k + 1}") for k in range(N_CLIENT)]   # 每客户端一张卡（B′）
            ts = [threading.Thread(target=worker, args=cards[k]) for k in range(N_CLIENT)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=60)
            self.assertFalse(any(t.is_alive() for t in ts), "有客户端线程未收束（卡住）")
        finally:
            proc.terminate()
            proc.wait(timeout=20)
        return results

    def test_A_two_clients_chain_single_and_complete(self):
        self.base = _events(self.srv)
        results = self._two_http_clients()
        accepted = sum(v["appended"] for v in results.values())
        deduped = sum(v["deduped"] for v in results.values())
        refused = [x for v in results.values() for x in v["refused"]]
        self.assertEqual(refused, [], f"同进程并发不该有写被拒：{refused[:2]}")
        self.assertEqual(deduped, 0, f"内容各不相同却触发去重 ⇒ 去重判据有问题：{deduped}")
        self.assertEqual(accepted, N_CLIENT * N_WRITE,
                         f"入链数 ≠ 尝试数（丢写）：{accepted} vs {N_CLIENT * N_WRITE}")
        n, seqs = _verify_ledger(self.srv, "shared.db")
        self.assertEqual(n - self.base, accepted,
                         f"链增量 ≠ 接受写入数（账外多写或漏写）：Δ{n - self.base} vs {accepted}")
        self.assertEqual(sorted(seqs), list(range(1, n + 1)), "seq 有重号或断号")

    def test_A2_counting_is_discriminating(self):
        """判别力对照：`content_hash` 去重必须真去重 ⇒ 臂 A 的"链增量==接受数"才有指称。"""
        with _Http(self.server_py, self.libs, "one", grant="g1") as rpc:
            base = _events(self.srv)
            s1, t1 = _append(rpc, "shared.db", "dup-1", "同一段内容")
            s2, t2 = _append(rpc, "shared.db", "dup-2", "同一段内容")   # 换 id、内容不变
            self.assertEqual(s1, "appended", f"首写未入链：{t1[:_REFUSE_SNIP]}")
            self.assertEqual(s2, "deduped",
                             f"同内容换 id 未走去重分支 ⇒ 去重不判内容：{t2[:_LOG_SNIP]}")
            self.assertEqual(_events(self.srv) - base, 1,
                             f"两次尝试应只落一条事件：Δ{_events(self.srv) - base}")

    def test_A3_id_is_not_a_unique_key_measured(self):
        """现状钉桩（L2-2 入口证据，**不是**"应当如此"）：id 无唯一约束，去重只看内容。

        实测：同 id 写两段不同内容 ⇒ 两条都进链，而投影以 id 建键，**前一条在检索/晋升
        视角里消失**（链上仍在）。风险=客户端以为存了两个条目，按 id 只看得见后来那个。
        本条断言在 L2-2 落地后必须改写；改不动=没真修。
        """
        with _Http(self.server_py, self.libs, "dup", grant="g1") as rpc:
            base = _events(self.srv)
            s1, _x1 = _append(rpc, "shared.db", "same", "甲内容")
            s2, _x2 = _append(rpc, "shared.db", "same", "乙内容")
            self.assertEqual((s1, s2), ("appended", "appended"),
                             "同 id 不同内容未双双入链 ⇒ 与本条要钉的现状不符，须回看并同步 L2-2 登记")
            self.assertEqual(_events(self.srv) - base, 2, "两条没都进链")
            rv = rpc.request("tools/call", {"name": "memory_retrieve",
                                            "arguments": {"lib": "shared.db",
                                                          "query": "甲内容 乙内容", "k": 9}})
            txt = json.dumps(rv, ensure_ascii=False)
            self.assertNotIn("甲内容", txt,
                             "被覆盖的那条竟还可检索 ⇒ 投影语义已变（与本登记不符，须同步改写）")
            self.assertIn("乙内容", txt, "后写的那条应可见")

    # ── 臂 B：两个服务件进程写同一个库 ─────────────────────────────────
    def test_B_two_processes_never_both_claim_success_on_a_forked_chain(self):
        """跨进程真并发：允许拒（单写者纪律），**不允许**两边都成功而链分叉。"""
        from mcp_client import MCPClient            # 同目录夹具（stdio 客户端）
        base = _events(self.srv)
        clients, accepted = [], []
        for k in range(N_CLIENT):
            c = MCPClient([*PY, self.server_py, "--libs-root", self.libs], timeout=_PROC_WAIT,
                          env={**os.environ, "L2_GRANT": f"g{k + 1}"})   # B′：每进程一张卡
            c.request("initialize", {"protocolVersion": "2025-06-18",
                                     "clientInfo": {"name": f"proc{k}"}})
            clients.append(c)
        try:
            for k, c in enumerate(clients):                   # 先把两个进程都推进去（各一条占位）
                accepted.append(_append(c, "shared.db", f"warm-{k}", f"占位{k}"))
            for i in range(N_WRITE):
                for k, c in enumerate(clients):
                    accepted.append(_append(c, "shared.db", f"p{k}-{i}", f"进程{k} 第{i}条"))
        finally:
            for c in clients:
                c.p.terminate()
        n_ok = sum(1 for s, _t in accepted if s == "appended")
        dedup = sum(1 for s, _t in accepted if s == "deduped")
        self.assertEqual(dedup, 0, f"并写内容重复被去重 ⇒ 本臂计数不干净：{dedup}")
        for s, txt in accepted:
            if s == "refused":                                # 拒必须是说得出理由的拒
                self.assertTrue("REFUSE:" in txt or "DENY:" in txt,
                                f"失败但无机读拒因（等于没设防）：{txt[:_REFUSE_SNIP]}")
        n, seqs = _verify_ledger(self.srv, "shared.db")
        self.assertEqual(n - base, n_ok,
                         f"链增量与接受数不一致＝有写静默丢失：Δ{n - base} accepted={n_ok}")
        self.assertEqual(sorted(seqs), list(range(1, n + 1)), "跨进程并写后 seq 重号/断号")

    # ── 臂 C：来源可查 = 身份按卡分化（B′ 落地后的正向断言）──────────────
    def test_C_sources_view_shows_identity_per_card(self):
        """**B′ 已落地**（L2-2·R4-a）：接入键随传输层（HTTP 头），归属由帽决定——
        两客户端两张卡 ⇒ 账上**两个 actor**、各 8 条。本断言取代 W5a 的
        "全归一个 actor"现状钉桩（预注册 P2 判据：L2-2 落地须改写，本条即改写）。"""
        self._two_http_clients()
        rc, out = _run([self.server_py, "sources", "--libs-root", self.libs])
        self.assertEqual(rc, 0, out[-_LOG_SNIP:])
        acts = _actors(out)
        self.assertNotEqual(acts, set(), f"来源视图没读出任何 actor：{out[-_LOG_SNIP:]}")
        w = _writers(out)
        self.assertEqual(set(w), {"llm:local:g1", "llm:local:g2"},
                         f"发卡后 actor 应按卡分化（每卡 {N_WRITE} 条），实得 {sorted(w)}")
        self.assertEqual(w["llm:local:g1"], N_WRITE)
        self.assertEqual(w["llm:local:g2"], N_WRITE)
        self.assertNotIn("human:root", w,
                         "ops 身份竟成了 entry_append 的归属 ⇒ 写入通道被 admin 面代签，须查 _write_cap")

    def test_C2_no_key_and_bogus_key_denied(self):
        """B′ 负向：无接入键 → DENY:NO_CAP；键无对应帽 → DENY（不存在或已撤销）。
        协议载荷没有身份字段——"自报身份"这个攻击面从根上不存在。"""
        port = _free_port()
        proc = subprocess.Popen([*PY, self.server_py, "--http", f":{port}",
                                 "--libs-root", self.libs],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8")
        try:
            _wait_ready(port, proc)
            st, txt = _append(_Rpc(port), "shared.db", "nk-1", "无键写入")
            self.assertEqual(st, "refused")
            self.assertIn("DENY:NO_CAP", txt)
            self.assertIn("接入键", txt)
            st2, txt2 = _append(_Rpc(port, grant="ghost"), "shared.db", "nk-2", "错键写入")
            self.assertEqual(st2, "refused")
            self.assertIn("无对应帽", txt2)
            st3, txt3 = _append(_Rpc(port, grant="g1"), "shared.db", "ok-1", "持卡写入")
            self.assertEqual(st3, "appended", f"持正确卡却被拒：{txt3[:_REFUSE_SNIP]}")
        finally:
            proc.terminate()
            proc.wait(timeout=20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
