# -*- coding: utf-8 -*-
"""test_bridge.py — W4 桥接不变量测试（memsys→audit-kit 接入面）
不变量：宿主只走公开面 / 决策留痕入账 / 未注册 kind 拒 / 越权拒 / 幂等键在账本可查。
"""
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("..", "../../", "../../audit-kit/core", "../../audit-kit/ledger"):
    p = os.path.normpath(os.path.join(_HERE, sub))
    if p not in sys.path: sys.path.insert(0, p)

from bridge import MemoryLedger, MEMSYS_CAP, KINDS          # noqa: E402
from evocore import decision                                # noqa: E402  (S1：原 from engine import)
from ledger import LedgerError                              # noqa: E402
from gov_types import Capability, PathGlobScope             # noqa: E402


class TestBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memsys_w4_")
        self.mled = MemoryLedger(os.path.join(self.tmp, "mem.db"))

    def tearDown(self):
        self.mled.close()
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_leaves_trace_with_content_hash(self):
        r = self.mled.record_append("llm:x", "e1", {"content": "偏好深色", "type": "semantic"})
        self.assertEqual(r["kind"], "memory_append")
        self.assertIn("content_hash", r["payload"])
        self.assertEqual(self.mled.count(), 1)

    def test_decision_trace_goes_to_ledger(self):
        tr, win, lose = decision.adjudicate_conflict(
            [{"id": "a", "source": "agent", "importance": 9},
             {"id": "m", "source": "manual", "importance": 1}])
        r = self.mled.record_decision("fallback:rule", tr)
        self.assertEqual(r["kind"], "memory_adjudicate")
        self.assertEqual(r["payload"]["decision"], "keep:m")

    def test_lifecycle_registered_kinds(self):
        for kind in ("promotion", "attic_nomination", "tombstone"):
            r = self.mled.record_lifecycle("engine", {"kind": kind, "entry_id": "e1"})
            self.assertEqual(r["kind"], kind)

    def test_unregistered_kind_rejected(self):
        with self.assertRaises(ValueError):
            self.mled.record_lifecycle("engine", {"kind": "not_a_kind"})

    def test_cross_package_chain_intact(self):
        """跨包链衔接：memsys 事件与 audit-kit 自举事件同链（若同库混写）。"""
        r1 = self.mled.record_append("llm:x", "e1", {"c": 1})
        r2 = self.mled.record_hit("llm:x", "e1", "查询")
        self.assertEqual(r2["prev_hash"], r1["self_hash"])

    def test_revoked_or_wrong_cap_denied(self):
        """能力面仍生效：无 append_events 的令牌写账本必拒。"""
        from ledger import Ledger
        led = Ledger.open(os.path.join(self.tmp, "cap.db"))
        bad_cap = Capability("memory", PathGlobScope("events", "table"),
                             frozenset({"read"}))
        with self.assertRaises(LedgerError) as cm:
            led.append(bad_cap, "llm:x", "memory_append", {})
        self.assertTrue(cm.exception.args[0].startswith("DENY:NO_CAP"))
        led.close()

    def test_kinds_registry_matches_kinds_yml(self):
        """桥内注册表与 kinds.yml 声明对齐（防两套声明漂移——F3 教训）。"""
        yml = open(os.path.normpath(os.path.join(_HERE, "..", "kinds.yml")),
                   encoding="utf-8").read()
        for k in KINDS:
            if k in ("memory_append", "memory_retrieve_hit"):  # 桥自用扩展
                continue
            self.assertIn(k, yml, f"kind {k} 未在 kinds.yml 声明")


if __name__ == "__main__":
    unittest.main(verbosity=2)
