# -*- coding: utf-8 -*-
"""test_auditkit.py — audit-kit W0-W2 全量不变量测试（5.3 亲写）
不变量优先：非法状态不可表示 / append-only 物理强制 / 链不可伪造 / 越权必拒。
"""
import datetime
import os
import sqlite3
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("../core", "../ledger"):
    p = os.path.normpath(os.path.join(_HERE, sub))
    if p not in sys.path: sys.path.insert(0, p)

from gov_types import Capability, Event, PathGlobScope, ResourceRef, Verdict  # noqa: E402
from hashes import canonical_json, event_hash, genesis_prev                   # noqa: E402
from capabilities import check, issue_capability, APPEND_EVENTS               # noqa: E402
from ledger import Ledger, LedgerError                                        # noqa: E402

TODAY = datetime.date(2026, 9, 22)


def cap(can=("append_events",), **kw):
    d = dict(resource_kind="memory", scope=PathGlobScope("*", "table"),
             can=frozenset(can), expires="2026-12-31")
    d.update(kw)
    return Capability(**d)


class TestHashes(unittest.TestCase):
    def test_canonical_json_key_order_irrelevant(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}), canonical_json({"a": 2, "b": 1}))

    def test_event_hash_deterministic(self):
        self.assertEqual(event_hash(genesis_prev(), {"k": "v"}),
                         event_hash(genesis_prev(), {"k": "v"}))

    def test_different_payload_different_hash(self):
        self.assertNotEqual(event_hash("0" * 64, {"a": 1}), event_hash("0" * 64, {"a": 2}))

    def test_bad_prev_length_rejected(self):
        with self.assertRaises(ValueError): event_hash("short", {})

    def test_unicode_payload_stable(self):
        h = event_hash(genesis_prev(), {"q": "偏好深色主题"})
        self.assertEqual(h, event_hash(genesis_prev(), {"q": "偏好深色主题"}))
        self.assertEqual(len(h), 64)


class TestTypes(unittest.TestCase):
    def test_valid_construction(self):
        c = cap()
        self.assertTrue(c.is_expired(TODAY) is False)

    def test_cap_can_cannot_overlap_rejected(self):
        with self.assertRaises(ValueError):
            Capability("memory", PathGlobScope("*"), frozenset({"a"}), frozenset({"a"}))

    def test_cap_empty_can_rejected(self):
        with self.assertRaises(ValueError):
            Capability("memory", PathGlobScope("*"), frozenset())

    def test_cap_bad_expires_rejected(self):
        with self.assertRaises(ValueError):
            cap(expires="2026/12/31")

    def test_cap_expiry_endpoint_inclusive(self):
        c = cap(expires="2026-09-22")
        self.assertTrue(c.is_expired(datetime.date(2026, 9, 22)))   # 当天即过期
        self.assertFalse(c.is_expired(datetime.date(2026, 9, 21)))

    def test_scope_kind_mismatch_rejected(self):
        s = PathGlobScope("memsys/**", "memory")
        self.assertFalse(s.matches(ResourceRef("table", "memsys/x")))
        self.assertTrue(s.matches(ResourceRef("memory", "memsys/e1")))

    def test_event_bad_actor_rejected(self):
        with self.assertRaises(ValueError):
            Event(1, "2026-09-22T00:00:00", "root", "k", {}, genesis_prev(), "0" * 64)

    def test_event_bad_hash_shape_rejected(self):
        with self.assertRaises(ValueError):
            Event(1, "t", "ci:hook", "k", {}, "XYZ", "0" * 64)


class TestCapabilities(unittest.TestCase):
    def test_check_pass(self):
        v = check(cap(), APPEND_EVENTS, ResourceRef("table", "events"), now=TODAY)
        self.assertTrue(v.ok)

    def test_deny_no_cap(self):
        v = check(cap(can=("read",)), APPEND_EVENTS, ResourceRef("table", "events"), now=TODAY)
        self.assertFalse(v.ok); self.assertTrue(v.detail.startswith("DENY:NO_CAP"))

    def test_deny_scope(self):
        v = check(cap(scope=PathGlobScope("other/**", "table")),
                  APPEND_EVENTS, ResourceRef("table", "events"), now=TODAY)
        self.assertFalse(v.ok); self.assertTrue(v.detail.startswith("DENY:SCOPE"))

    def test_deny_expired(self):
        v = check(cap(expires="2026-09-01"), APPEND_EVENTS,
                  ResourceRef("table", "events"), now=TODAY)
        self.assertFalse(v.ok); self.assertTrue(v.detail.startswith("DENY:EXPIRED"))

    def test_issue_payload_shape(self):
        p = issue_capability("memory", PathGlobScope("m/**"), ["append_events"])
        self.assertEqual(p["kind"], "capability_issue")
        self.assertIn("append_events", p["capability"]["can"])


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ak_ledger_")
        self.path = os.path.join(self.tmp, "t.db")

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def _open(self):
        return Ledger.open(self.path)

    def test_open_idempotent(self):
        led = self._open(); led.append(cap(), "human:a", "t1", {"x": 1}); led.close()
        led2 = self._open()                      # 二次 open=验证+幂等
        self.assertEqual(led2.count(), 1); led2.close()

    def test_append_and_chain(self):
        led = self._open()
        r1 = led.append(cap(), "ci:hook", "anchor", {"n": 1})
        r2 = led.append(cap(), "ci:hook", "anchor", {"n": 2})
        self.assertEqual(r1["prev_hash"], genesis_prev())        # 链首接 genesis
        self.assertEqual(r2["prev_hash"], r1["self_hash"])       # 链尾衔接
        led.verify(); led.close()                                 # 重放通过

    def test_denied_append_raises_before_insert(self):
        led = self._open()
        with self.assertRaises(LedgerError) as cm:
            led.append(cap(can=("read",)), "llm:x", "t", {})
        self.assertTrue(cm.exception.args[0].startswith("DENY:NO_CAP"))
        self.assertEqual(led.count(), 0)                          # 未插入
        led.close()

    def test_update_physically_aborted(self):
        led = self._open(); led.append(cap(), "human:a", "k", {"a": 1}); led.close()
        conn = sqlite3.connect(self.path)                          # 外部连接直改
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE events SET kind='hacked' WHERE seq=1")
        conn.close()

    def test_delete_physically_aborted(self):
        led = self._open(); led.append(cap(), "human:a", "k", {}); led.close()
        conn = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM events")
        conn.close()

    def test_verify_detects_forged_row(self):
        led = self._open(); led.append(cap(), "human:a", "k", {"a": 1}); led.close()
        conn = sqlite3.connect(self.path)
        conn.execute("DROP TRIGGER no_update")                     # 摘触发器后伪造
        conn.execute("UPDATE events SET payload='{\"a\":2}' WHERE seq=1")
        conn.execute("CREATE TRIGGER no_update BEFORE UPDATE ON events "
                     "BEGIN SELECT RAISE(ABORT,'x'); END")         # 触发器放回
        conn.commit(); conn.close()
        with self.assertRaises(LedgerError):                       # 重放抓到哈希不符
            self._open()

    def test_missing_trigger_detected_at_open(self):
        led = self._open(); led.append(cap(), "human:a", "k", {}); led.close()
        conn = sqlite3.connect(self.path)
        conn.execute("DROP TRIGGER no_delete"); conn.commit(); conn.close()
        with self.assertRaises(LedgerError):
            self._open()


if __name__ == "__main__":
    unittest.main(verbosity=2)
