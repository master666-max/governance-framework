# -*- coding: utf-8 -*-
"""test_server.py — L2-0 服务件不变量测试（S4 · T5/T10；《S4设计》§五 判据 1/2/3/5/6/7）

守的契约（负向必配正向对照）：
  ① 客户端连上跑通：initialize 协商 · tools/list=**8** · 八工具全路径 ok；
  ② 留痕与链完整：写工具产生对应 kind；memory_verify 通过；
  ③ caps 路径真实：空表→DENY:NO_CAP；`grant` 后→放行且 `capability_issue` 在账；
  ④ 幂等去重：同 content 二次 append → deduped；
  ⑤ 判别力六式：篡改库 / 未知工具 / 畸形报文 / 坏库名 / 超长内容 / 目录越界——**必拒**；
  ⑥ 多库独立 + HTTP 绑定同核 + stats 读数。
运行：py -X utf8 build/tests/test_server.py
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCPClient, TOOLS8, free_port  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "build", "out", "server")
OVERSIZE_CONTENT = 30000   # 超长内容样本（>服务件 MAX_CONTENT=20000）
E_PARSE = -32700           # JSON-RPC Parse error（与 server 常量同值）
_TMP = []


def _deploy(name="srv"):
    d = tempfile.mkdtemp(prefix=f"s4_{name}_")
    _TMP.append(d)
    srv = os.path.join(d, "server")
    shutil.copytree(SRC, srv, ignore=shutil.ignore_patterns("__pycache__", "calls.jsonl", "caps.json"))
    return srv


def _run(argv):
    r = subprocess.run([sys.executable, "-X", "utf8", *argv], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = _deploy("main")
        rc, log = _run([os.path.join(cls.srv, "server.py"), "init", "--libs-root",
                        os.path.join(cls.srv, "libs"), "--lib", "t.db", "--grant-id", "g1"])
        assert rc == 0, log
        cls.c = MCPClient([sys.executable, "-X", "utf8", os.path.join(cls.srv, "server.py"),
                           "--libs-root", os.path.join(cls.srv, "libs")],
                          env={**os.environ, "L2_GRANT": "g1"})
        cls.c.request("initialize", {"protocolVersion": "2025-06-18"})
        cls.c.notify("notifications/initialized")

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        for d in _TMP:
            shutil.rmtree(d, ignore_errors=True)

    def _append(self, eid, content, **kw):
        args = {"lib": "t.db", "id": eid, "content": content, "keywords": ["样本"],
                "type": "procedural", "importance": 8, **kw}
        return self.c.call_tool("memory_append", args)

    def test_initialize_and_tools_list(self):
        """① tools/list 恰八件；initialize 协商回显。"""
        tools = [t["name"] for t in self.c.request("tools/list")["tools"]]
        self.assertEqual(tools, TOOLS8)
        init = self.c.request("initialize", {"protocolVersion": "2024-11-05"})
        self.assertEqual(init["protocolVersion"], "2024-11-05")     # 回显受支持版本
        self.assertEqual(init["capabilities"]["tools"]["listChanged"], False)

    def test_full_roundtrip_and_ledger(self):
        """①② 八工具全路径 + 留痕与链完整。"""
        ok, r1, meta = self._append("e1", "玻璃材质 IOR 1.45")
        self.assertTrue(ok, r1)
        self.assertGreater(r1["seq"], 1)                            # seq1=capability_issue（签发在账）
        ok2, r2, _ = self._append("e2", "三点布光 主光 45 度")
        self.assertTrue(ok2, r2)
        ok3, hits, m3 = self.c.call_tool("memory_retrieve", {"lib": "t.db", "query": "玻璃 材质", "k": 3})
        self.assertTrue(ok3, hits)
        self.assertIn("ms", m3)                                     # G6 观测位在外
        ok4, p4, _ = self.c.call_tool("memory_promote", {"lib": "t.db", "id": "e1"})
        self.assertTrue(ok4, p4)
        ok5, p5, _ = self.c.call_tool("memory_tombstone", {"lib": "t.db", "id": "e2"})
        self.assertTrue(ok5, p5)
        ok6, v6, _ = self.c.call_tool("memory_verify", {"lib": "t.db"})
        self.assertTrue(ok6 and v6["ok"], v6)
        ok7, a7, _ = self.c.call_tool("anchor", {"lib": "t.db"})
        self.assertTrue(ok7 and a7["ledger_head"], a7)
        ok8, s8, _ = self.c.call_tool("scan", {"lib": "t.db", "dir": "."})
        self.assertTrue(ok8, s8)
        ok9, j9, _ = self.c.call_tool("adjudicate", {"lib": "t.db", "intent": "merge", "ids": ["e1", "e2"]})
        self.assertTrue(ok9, j9)
        self.assertEqual(j9["trace"]["decision"], "defer")          # merge 恒 defer（保守拒绝）
        con = sqlite3.connect(os.path.join(self.srv, "libs", "t.db"))
        kinds = {k for (k,) in con.execute("SELECT DISTINCT kind FROM events")}
        con.close()
        for want in ("capability_issue", "entry_append", "retrieve_hit", "promotion",
                     "tombstone", "anchor", "anchor_scan", "memory_adjudicate"):
            self.assertIn(want, kinds, f"缺 kind={want}（{sorted(kinds)}）")

    def test_dedupe_same_content(self):
        """④ 幂等：同 content 二次 append → deduped。"""
        self._append("d1", "去重样本：材质基材")
        ok, r, _ = self._append("d1b", "去重样本：材质基材")
        self.assertTrue(ok and r.get("deduped") is True, r)

    def test_refuses_bad_inputs(self):
        """⑤ 判别力：坏库名 / 超长内容 / 目录越界 / 未知工具 / 畸形报文——必拒。"""
        ok, r, _ = self.c.call_tool("memory_append", {"lib": "../evil.db", "id": "x", "content": "c"})
        self.assertFalse(ok, "越界库名未被拒")
        self.assertIn("REFUSE", r["error"])
        ok, r, _ = self.c.call_tool("memory_append", {"lib": "t.db", "id": "x",
                                                       "content": "y" * OVERSIZE_CONTENT})
        self.assertFalse(ok, "超长内容未被拒")
        ok, r, _ = self.c.call_tool("scan", {"lib": "t.db", "dir": "../../.."})
        self.assertFalse(ok, "目录越界未被拒")
        with self.assertRaises(RuntimeError):                       # 未知工具 → JSON-RPC 错误
            self.c.request("tools/call", {"name": "no_such_tool", "arguments": {}})
        msg = self.c.raw("{not json")
        self.assertIsNotNone(msg, "畸形报文无响应")
        self.assertEqual(msg.get("error", {}).get("code"), E_PARSE)

    def test_verify_detects_tamper(self):
        """⑤ 篡改库 → memory_verify 必 FAIL（负向）；干净库 PASS（正向）。"""
        srv2 = _deploy("tamper")
        _run([os.path.join(srv2, "server.py"), "init", "--libs-root", os.path.join(srv2, "libs"),
              "--lib", "x.db"])
        c2 = MCPClient([sys.executable, "-X", "utf8", os.path.join(srv2, "server.py"),
                        "--libs-root", os.path.join(srv2, "libs")],
                       env={**os.environ, "L2_GRANT": "g1"})
        try:
            c2.request("initialize", {})
            ok, p, _ = c2.call_tool("memory_append", {"lib": "x.db", "id": "a", "content": "样本"})
            self.assertTrue(ok, p)
            db = os.path.join(srv2, "libs", "x.db")
            con = sqlite3.connect(db)
            con.executescript("DROP TRIGGER no_update; DROP TRIGGER no_delete;")
            con.execute("UPDATE events SET actor='human:evil' WHERE seq=2")
            con.commit()
            con.close()
            ok2, v2, _ = c2.call_tool("memory_verify", {"lib": "x.db"})
            self.assertFalse(ok2, "篡改未被检出")
            self.assertIn("FAIL", v2["error"])
        finally:
            c2.close()

    def test_cap_denied_then_granted(self):
        """③ 空表→DENY:NO_CAP；grant 后放行且 capability_issue 在账。"""
        srv3 = _deploy("caps")
        _run([os.path.join(srv3, "server.py"), "init", "--libs-root", os.path.join(srv3, "libs"),
              "--lib", "c.db"])
        with open(os.path.join(srv3, "libs", "caps.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"caps": []}, f, ensure_ascii=False)          # 清空=空表不预填（caps 权威位=libs_root·P2 作用域修复）
        c3 = MCPClient([sys.executable, "-X", "utf8", os.path.join(srv3, "server.py"),
                        "--libs-root", os.path.join(srv3, "libs")])
        try:
            c3.request("initialize", {})
            ok, r, _ = c3.call_tool("memory_append", {"lib": "c.db", "id": "a", "content": "x"})
            self.assertFalse(ok, "空表却放行")
            self.assertIn("DENY:NO_CAP", r["error"])
        finally:
            c3.close()
        rc, log = _run([os.path.join(srv3, "server.py"), "grant", "--libs-root",
                        os.path.join(srv3, "libs"), "--grant-id", "g9", "--actor-prefix", "llm:test"])
        self.assertEqual(rc, 0, log)
        c4 = MCPClient([sys.executable, "-X", "utf8", os.path.join(srv3, "server.py"),
                        "--libs-root", os.path.join(srv3, "libs")],
                       env={**os.environ, "L2_GRANT": "g9"})
        try:
            c4.request("initialize", {})
            ok, r, _ = c4.call_tool("memory_append", {"lib": "c.db", "id": "a", "content": "x"})
            self.assertTrue(ok, r)
        finally:
            c4.close()
        con = sqlite3.connect(os.path.join(srv3, "libs", "c.db"))
        n = con.execute("SELECT COUNT(*) FROM events WHERE kind='capability_issue'").fetchone()[0]
        con.close()
        self.assertGreaterEqual(n, 2, "签发事件未入账（应≥2：init 一枚 + grant 一枚）")

    def test_multi_lib_isolation(self):
        """⑥ 两库独立（链各自完整；库名白名单内）。"""
        _run([os.path.join(self.srv, "server.py"), "init", "--libs-root",
              os.path.join(self.srv, "libs"), "--lib", "second.db", "--grant-id", "g1"])
        ok, p, _ = self.c.call_tool("memory_append", {"lib": "second.db", "id": "s", "content": "第二库样本"})
        self.assertTrue(ok, p)
        ok1, v1, _ = self.c.call_tool("memory_verify", {"lib": "t.db"})
        ok2, v2, _ = self.c.call_tool("memory_verify", {"lib": "second.db"})
        self.assertTrue(ok1 and ok2)
        self.assertNotEqual(v1["head"], v2["head"], "两库链头不应相同")

    def test_http_transport_smoke(self):
        """⑥ HTTP 绑定同核（POST /mcp）。"""
        port = free_port()
        srv4 = _deploy("http")
        _run([os.path.join(srv4, "server.py"), "init", "--libs-root", os.path.join(srv4, "libs"),
              "--lib", "h.db"])
        p = subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(srv4, "server.py"),
                              "--libs-root", os.path.join(srv4, "libs"), "--http", f":{port}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            url = f"http://127.0.0.1:{port}/mcp"
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2025-06-18"}}).encode()
            last = None
            for _ in range(40):                     # 等端口就绪
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=2) as resp:
                        last = json.loads(resp.read().decode("utf-8"))
                    break
                except OSError as e:
                    last = str(e)
                    import time as _t
                    _t.sleep(0.25)
            self.assertIsInstance(last, dict, f"HTTP 未就绪：{last}")
            self.assertIn(last["result"]["protocolVersion"], ("2025-06-18", "2025-03-26", "2024-11-05"))
            body2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                "params": {"name": "memory_verify", "arguments": {"lib": "h.db"}}}).encode()
            with urllib.request.urlopen(urllib.request.Request(
                    url, data=body2, headers={"X-L2-Grant": "g1"}), timeout=5) as resp:
                r2 = json.loads(resp.read().decode("utf-8"))
            self.assertFalse(r2["result"]["isError"], r2)
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

    def test_stats_readings(self):
        """⑥ stats 读数（G6；调用日志聚合）。"""
        rc, out = _run([os.path.join(self.srv, "server.py"), "stats", "--libs-root",
                        os.path.join(self.srv, "libs")])
        self.assertEqual(rc, 0, out)
        self.assertIn("memory_append", out)
        self.assertIn("p50 ms", out)


class TestSingleWriter(unittest.TestCase):
    def test_busy_external_writer_refused(self):
        """单写者纪律：外部写者占库 → 服务件拒（fail-closed，不硬重试）。"""
        srv = _deploy("busy")
        _run([os.path.join(srv, "server.py"), "init", "--libs-root", os.path.join(srv, "libs"),
              "--lib", "b.db"])
        db = os.path.join(srv, "libs", "b.db")
        holder = sqlite3.connect(db, isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")                          # 占住 RESERVED 锁
        c = MCPClient([sys.executable, "-X", "utf8", os.path.join(srv, "server.py"),
                       "--libs-root", os.path.join(srv, "libs")],
                      env={**os.environ, "L2_GRANT": "g1"})
        try:
            c.request("initialize", {})
            ok, r, _ = c.call_tool("memory_append", {"lib": "b.db", "id": "a", "content": "x"})
            self.assertFalse(ok, "被占用却放行")
            self.assertIn("REFUSE", r["error"])
        finally:
            c.close()
            holder.execute("ROLLBACK")
            holder.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
