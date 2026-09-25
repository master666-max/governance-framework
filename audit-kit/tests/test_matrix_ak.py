# -*- coding: utf-8 -*-
"""test_matrix_ak.py — audit-kit 边界矩阵测试（W4 扩写，独立于 test_auditkit.py）
每条用例守一个明确不变量（原两处 expectedFailure 已随实现修复转正）
的已知偏差（见交付 deviations），实现修复后须摘标并转正。
"""
import dataclasses
import datetime
import json
import os
import sys
import tempfile
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("../core", "../ledger"):
    p = os.path.normpath(os.path.join(_HERE, sub))
    if p not in sys.path: sys.path.insert(0, p)

from gov_types import Capability, Event, PathGlobScope, ResourceRef  # noqa: E402
from hashes import canonical_json, event_hash, genesis_prev           # noqa: E402
from capabilities import check, issue_capability, APPEND_EVENTS       # noqa: E402
from ledger import Ledger, LedgerError                                # noqa: E402

TODAY = datetime.date(2026, 9, 22)


def _evt(**over):
    """合法 Event 基座，仅覆盖指定字段。"""
    d = dict(seq=1, ts="2026-09-22T00:00:00", actor="ci:hook", kind="k",
             payload={"a": 1}, prev_hash=genesis_prev(), self_hash="a" * 64)
    d.update(over)
    return Event(**d)


def mk_cap(can=(APPEND_EVENTS,), **kw):
    """默认可写账本表的能力；expires=None 使用例不依赖运行日期。"""
    d = dict(resource_kind="table", scope=PathGlobScope("*", "table"),
             can=frozenset(can), expires=None)
    d.update(kw)
    return Capability(**d)


class TestGovTypesEdges(unittest.TestCase):
    def test_event_seq_below_one_rejected(self):
        # 守不变量：seq 从 1 起（0 无位次、负数无意义，构造即拒）
        with self.assertRaises(ValueError):
            _evt(seq=0)
        with self.assertRaises(ValueError):
            _evt(seq=-1)

    def test_event_payload_unserializable_rejected(self):
        # 守不变量：payload 必须 JSON 可序列化（set 无 JSON 对应物，构造即拒）
        with self.assertRaises(ValueError):
            _evt(payload={"s": {1, 2}})

    def test_event_hash_fields_lowercase_hex_only(self):
        # 守不变量：prev_hash/self_hash 字符域为小写十六进制（大写/混排皆拒）
        with self.assertRaises(ValueError):
            _evt(prev_hash="A" * 64)
        with self.assertRaises(ValueError):
            _evt(prev_hash="a" * 63 + "F")
        with self.assertRaises(ValueError):
            _evt(self_hash="B" * 64)

    def test_event_frozen(self):
        # 守不变量：Event 冻结不可变（账本行入账后内存形态也不许改）
        e = _evt()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.kind = "hacked"

    def test_capability_expires_illegal_calendar_date_rejected(self):
        # 守 P7 契约：非法日历日期在构造时即拒（gov_types 头注"非法值在构造时抛
        # ValueError"）。实现现状：2026-13-01 过形状正则、构造放行，is_expired 才炸。
        with self.assertRaises(ValueError):
            Capability("memory", PathGlobScope("*"), frozenset({"a"}),
                       expires="2026-13-01")

    def test_scope_empty_pattern_rejected(self):
        # 守不变量：空 pattern 不成作用域（匹配任何路径的"空规则"不可表示）
        with self.assertRaises(ValueError):
            PathGlobScope("")

    def test_scope_default_kind_wildcard(self):
        # 守不变量：resource_kind 缺省为通配（任意 kind 皆可命中，路径仍受 pattern 约束）
        s = PathGlobScope("memsys/*")
        self.assertTrue(s.matches(ResourceRef("anything", "memsys/e1")))
        self.assertFalse(s.matches(ResourceRef("anything", "other/e1")))

    def test_resource_ref_empty_field_rejected(self):
        # 守不变量：ResourceRef 两字段皆不可空（无 kind 或无路径的引用不可表示）
        with self.assertRaises(ValueError):
            ResourceRef("", "p")
        with self.assertRaises(ValueError):
            ResourceRef("memory", "")


class TestHashesMatrix(unittest.TestCase):
    def test_canonical_json_nested_key_order_stable(self):
        # 守不变量：任意深度嵌套结构，键的插入顺序不影响 canonical 串（列表序除外）
        a = {"x": {"p": 1, "q": [{"m": 1, "n": 2}]}, "y": [3, 1]}
        b = {"y": [3, 1], "x": {"q": [{"n": 2, "m": 1}], "p": 1}}
        self.assertEqual(canonical_json(a), canonical_json(b))

    def test_canonical_json_keeps_unicode(self):
        # 守不变量：canonical 保 unicode 原文（ensure_ascii=False），中文不折成 \u 转义
        s = canonical_json({"q": "偏好深色主题"})
        self.assertIn("偏好深色主题", s)
        self.assertNotIn("\\u", s)

    def test_event_hash_insensitive_to_dict_insertion_order(self):
        # 守不变量：同一 payload 的不同构造顺序得同一事件哈希（等价则同哈希、异质则异哈希）
        p1 = {"actor": "llm:x", "kind": "k", "body": {"b": 2, "a": 1}}
        p2 = {"body": {"a": 1, "b": 2}, "kind": "k", "actor": "llm:x"}
        self.assertEqual(event_hash(genesis_prev(), p1),
                         event_hash(genesis_prev(), p2))
        self.assertNotEqual(event_hash(genesis_prev(), p1),
                            event_hash(genesis_prev(), {"actor": "llm:x", "kind": "k",
                                                        "body": {"b": 2, "a": 2}}))

    def test_event_hash_rejects_non_hex_prev(self):
        # 守契约：prev_hash 字符域须十六进制（hashes.py 报错文案自述"须 64 位十六
        # 进制"）。实现现状：只查长度，64 位非十六进制串静默产出哈希。
        with self.assertRaises(ValueError):
            event_hash("z" * 64, {"k": 1})
        with self.assertRaises(ValueError):  # 对照：长度非 64 现已被拒
            event_hash("z" * 63, {"k": 1})


class TestCapabilityGateOrder(unittest.TestCase):
    def test_gate_order_no_cap_reported_first(self):
        # 守不变量：四关同违（无此动作+越界+过期）时报第一关 DENY:NO_CAP
        c = mk_cap(can=("read",), scope=PathGlobScope("nope/**", "table"),
                   expires="2026-01-01")
        v = check(c, APPEND_EVENTS, ResourceRef("table", "events"), now=TODAY)
        self.assertTrue(v.detail.startswith("DENY:NO_CAP"))

    def test_gate_order_scope_reported_second(self):
        # 守不变量：动作在 can 但越界+过期时报第二关 DENY:SCOPE（不跳报 EXPIRED）
        c = mk_cap(scope=PathGlobScope("nope/**", "table"), expires="2026-01-01")
        v = check(c, APPEND_EVENTS, ResourceRef("table", "events"), now=TODAY)
        self.assertTrue(v.detail.startswith("DENY:SCOPE"))

    def test_gate_order_cannot_before_expired(self):
        # 守不变量：CANNOT 关先于 EXPIRED 关。经构造校验的 Capability 恒有
        # can∩cannot=∅（第三关走不到），故以鸭子类型立起第四关与第三关的先后。
        stand_in = types.SimpleNamespace(
            can=frozenset({"append_events", "delete"}),
            scope=PathGlobScope("*", "table"),
            cannot=frozenset({"delete"}),
            is_expired=lambda now: True)
        v = check(stand_in, "delete", ResourceRef("table", "events"), now=TODAY)
        self.assertTrue(v.detail.startswith("DENY:CANNOT"))

    def test_gate_expired_reported_last(self):
        # 守不变量：前三关全过、仅过期时才报 DENY:EXPIRED（末关不抢跑）
        c = mk_cap(expires="2026-01-01")
        v = check(c, APPEND_EVENTS, ResourceRef("table", "events"), now=TODAY)
        self.assertTrue(v.detail.startswith("DENY:EXPIRED"))

    def test_issue_capability_overlap_cannot_raises(self):
        # 守不变量：can/cannot 重叠的令牌签不出来（Capability 构造即拒，重叠经
        # issue_capability 同样到不了 payload）
        with self.assertRaises(ValueError):
            issue_capability("memory", PathGlobScope("*"), ["a"], cannot=["a"])

    def test_issue_payload_can_sorted_deterministic(self):
        # 守不变量：签发 payload 的 can/cannot 恒为排序列表（同输入同 payload，
        # 入账哈希才可复算）
        p = issue_capability("memory", PathGlobScope("*"),
                             ["write", "append_events", "read"])
        self.assertEqual(p["capability"]["can"],
                         ["append_events", "read", "write"])


class TestLedgerMatrix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ak_matrix_")
        self.path = os.path.join(self.tmp, "t.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _open(self):
        return Ledger.open(self.path)

    def test_empty_ledger_head_is_genesis(self):
        # 守不变量：空库 head 即 genesis（链首 prev 有定义，verify 空放亦通过）
        led = self._open()
        self.assertEqual(led.head(), genesis_prev())
        self.assertEqual(led.count(), 0)
        led.verify()
        led.close()

    def test_hundred_appends_verify_and_head_stable(self):
        # 守不变量：连续 100 条 append 后链重放通过、count=100、head 稳定且即末行哈希
        led = self._open()
        for i in range(100):
            led.append(mk_cap(), "llm:agent", "bulk", {"i": i})
        led.verify()
        self.assertEqual(led.count(), 100)
        self.assertEqual(led.head(), led.head())
        self.assertEqual(led.head(), list(led.rows())[-1][6])
        led.close()

    def test_append_chinese_emoji_payload_roundtrip(self):
        # 守不变量：中文/emoji payload 入账后无损往返（返回值、库行、重放三处一致）
        led = self._open()
        p = {"q": "偏好深色主题", "emoji": "🧠😀", "nested": {"标签": "记忆"}}
        r = led.append(mk_cap(), "llm:助手", "note", p)
        self.assertEqual(r["payload"], p)
        led.verify()
        row = list(led.rows())[0]
        self.assertEqual(json.loads(row[4]), p)
        led.close()

    def test_rows_ordered_by_seq(self):
        # 守不变量：rows() 输出即 seq 升序的链本身（首行接 genesis，逐行 prev 衔接）
        led = self._open()
        for i in range(5):
            led.append(mk_cap(), "ci:hook", "k", {"i": i})
        rs = list(led.rows())
        self.assertEqual([r[0] for r in rs], [1, 2, 3, 4, 5])
        self.assertEqual(rs[0][5], genesis_prev())
        for prev_row, row in zip(rs, rs[1:]):
            self.assertEqual(row[5], prev_row[6])
        led.close()


class TestFullChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ak_chain_")
        self.path = os.path.join(self.tmp, "t.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _open(self):
        return Ledger.open(self.path)

    def test_issue_check_append_full_chain(self):
        # 守不变量：签发→校验→入账全链自洽——issue_capability 的 payload 原样入账
        # 可重放；从 payload 重建的能力对其辖域资源 check 通过。
        led = self._open()
        payload = issue_capability("memory", PathGlobScope("memsys/**", "memory"),
                                   ["append_events"], actor="human:root")
        r1 = led.append(mk_cap(), "human:root", payload["kind"], payload)
        self.assertEqual(r1["prev_hash"], genesis_prev())
        c = payload["capability"]
        holder = Capability(c["resource_kind"],
                            PathGlobScope(c["scope_pattern"], c["resource_kind"]),
                            frozenset(c["can"]))
        self.assertTrue(check(holder, "append_events",
                              ResourceRef("memory", "memsys/e1.json"),
                              now=TODAY).ok)
        led.verify()
        self.assertEqual(led.count(), 1)
        self.assertEqual(led.head(), r1["self_hash"])
        self.assertEqual(json.loads(next(iter(led.rows()))[4]), payload)
        led.close()

    def test_issued_cap_cannot_write_ledger(self):
        # 守不变量：签发给持有人（memory:memsys/**）的能力对账本表越界——校验
        # DENY:SCOPE，append 在插入前被拒（count 不变）。
        led = self._open()
        payload = issue_capability("memory", PathGlobScope("memsys/**", "memory"),
                                   ["append_events"])
        c = payload["capability"]
        holder = Capability(c["resource_kind"],
                            PathGlobScope(c["scope_pattern"], c["resource_kind"]),
                            frozenset(c["can"]))
        v = check(holder, APPEND_EVENTS, ResourceRef("table", "events"), now=TODAY)
        self.assertFalse(v.ok)
        self.assertTrue(v.detail.startswith("DENY:SCOPE"))
        with self.assertRaises(LedgerError):
            led.append(holder, "llm:agent", "x", {"a": 1})
        self.assertEqual(led.count(), 0)
        led.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
