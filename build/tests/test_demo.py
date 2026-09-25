# -*- coding: utf-8 -*-
"""test_demo.py — S5 端到端演示不变量测试（S5 · T3；《S5设计》§五 判据 8 等）

守的契约：
  ① 演示可跑通：五段全绿（exit 0）+ REPORT/demo.json 落盘；
  ② **可重复**：连跑两次——跨形态排名一致、段3 账内条目集一致、段4 三同均过；
  ③ 四条验收原文在案：微内核自检 / 中库建库检索 / 共库双客户端并写（4 条入账）/
     升格直迁（three_same+db_sha_equal+MCP verify）；
  ④ 对照段零差异（或挂 D 号——本实现：差异非空即非零退出）；
  ⑤ T1 缺陷反转：kb 投影含 created_at；融合件墓碑后检索为空；
  ⑥ 判别力（负向）：篡改升格后的库 → MCP memory_verify 必 FAIL（干净态 PASS 作正向对照）。
运行：py -X utf8 build/tests/test_demo.py
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO = os.path.join(ROOT, "build", "demo_e2e.py")
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)
from mcp_client import MCPClient  # noqa: E402

_TMP = []
OUT_SNIPPET = 800          # 失败输出摘录长度


def _tmp(name):
    d = tempfile.mkdtemp(prefix=f"s5demo_{name}_")
    _TMP.append(d)
    return d


def _demo(root):
    r = subprocess.run([sys.executable, "-X", "utf8", DEMO, "--root", root],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    data = None
    p = os.path.join(root, "demo.json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    return r.returncode, r.stdout, data


class TestDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roots = [_tmp("run1"), _tmp("run2")]
        cls.results = [_demo(r) for r in cls.roots]
        cls.rcs = [x[0] for x in cls.results]
        cls.datas = [x[2] for x in cls.results]

    @classmethod
    def tearDownClass(cls):
        for d in _TMP:
            shutil.rmtree(d, ignore_errors=True)

    def test_demo_runs_clean_and_reports(self):
        """① 两跑 exit 0；REPORT.md/demo.json 落盘且五段齐。"""
        for rc, out, data in self.results:
            self.assertEqual(rc, 0, out[-OUT_SNIPPET:])
            self.assertIsNotNone(data, "demo.json 缺失")
        segs = set(self.datas[0]["segments"])
        self.assertEqual(segs, {"seg1_fused", "seg2_kb", "seg3_server", "seg4_promote"})
        for root in self.roots:
            self.assertTrue(os.path.isfile(os.path.join(root, "REPORT.md")))

    def test_acceptance_four_items_in_place(self):
        """③ 四条验收原文逐条在案（微内核自检/中库建库检索/双客户端并写/升格链完整）。"""
        d = self.datas[0]
        self.assertEqual(d["segments"]["seg1_fused"]["selftest"], "OK")
        self.assertIn("framework_sha=622110a5af2cc4d7", d["segments"]["seg1_fused"]["verify"])
        self.assertIn("注入 4", d["segments"]["seg2_kb"]["import"])
        self.assertEqual(d["segments"]["seg2_kb"]["query"], ["e1", "e3"])
        seg3 = d["segments"]["seg3_server"]
        self.assertEqual(seg3["entries_in_ledger"], ["a1", "a2", "b1", "b2"])   # 双客户端各 2 条
        self.assertTrue(seg3["verify"]["ok"])
        seg4 = d["segments"]["seg4_promote"]
        self.assertTrue(seg4["three_same"]["pass"])
        self.assertTrue(seg4["three_same"]["db_sha_equal"])
        self.assertTrue(seg4["mcp_verify"]["ok"])
        self.assertEqual(seg4["mcp_retrieve"], ["e1", "e3"])

    def test_repeatable_across_runs(self):
        """② 可重复：两跑排名/条目集/三同判据一致。"""
        a, b = self.datas
        self.assertEqual(a["comparison"]["rows"], b["comparison"]["rows"])
        self.assertEqual(a["segments"]["seg3_server"]["entries_in_ledger"],
                         b["segments"]["seg3_server"]["entries_in_ledger"])
        self.assertEqual(a["segments"]["seg4_promote"]["three_same"]["digest"],
                         b["segments"]["seg4_promote"]["three_same"]["digest"])
        self.assertEqual(a["segments"]["seg1_fused"]["retrieve"],
                         b["segments"]["seg1_fused"]["retrieve"])

    def test_comparison_zero_diff(self):
        """④ 对照段零差异（非空即应挂 D 号——本实现以非零退出表达，此处置失败即闸）。"""
        for rc, out, data in self.results:
            self.assertEqual(data["comparison"]["diffs"], [], f"未登记差异：{data['comparison']['diffs']}")
            self.assertEqual(rc, 0, "差异非空应导致非零退出")

    def test_t1_defect_probes_reversed(self):
        """⑤ T1 两缺陷反转（kb 投影含 created_at；融合件墓碑后检索为空）。"""
        for data in self.datas:
            probes = data["t1_defects"]
            self.assertTrue(probes["kb_projection_has_created_at"])
            self.assertEqual(probes["created_at_sample"], "2026-08-01T00:00:00")
            self.assertTrue(probes["fused_tombstone_exits"])

    def test_tamper_promoted_lib_detected(self):
        """⑥ 判别力：篡改升格后的库 → MCP memory_verify 必 FAIL（正向对照同跑）。"""
        root = self.roots[0]
        l2 = os.path.join(root, "l2")
        lib = os.path.join(l2, "libs", "promoted.db")
        c = MCPClient([sys.executable, "-X", "utf8", os.path.join(l2, "server.py"),
                       "--libs-root", os.path.join(l2, "libs")])
        try:
            c.request("initialize", {})
            ok0, v0, _ = c.call_tool("memory_verify", {"lib": "promoted.db"})    # 正向：干净态 PASS
            self.assertTrue(ok0 and v0["ok"], v0)
            con = sqlite3.connect(lib, isolation_level=None)
            con.executescript("DROP TRIGGER no_update; DROP TRIGGER no_delete;")
            con.execute("UPDATE events SET actor='human:evil' WHERE seq=1")
            con.commit()
            con.close()
            ok1, v1, _ = c.call_tool("memory_verify", {"lib": "promoted.db"})    # 负向：必 FAIL
            self.assertFalse(ok1, "篡改未被检出")
            self.assertIn("FAIL", v1["error"])
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
