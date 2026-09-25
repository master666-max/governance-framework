# -*- coding: utf-8 -*-
"""test_evocore_project.py — 事件流投影测试（S4/T1；`evocore/project.py`）

守的契约：
  ① entry_append 建条（id=entry_id、content_hash 随行）；
  ② promotion → state=longterm（仅对已有条目）；
  ③ retrieve_hit → last_used_at=**账本行 ts**（D7 登记项：持久化按语义实现）；
  ④ tombstone → tombstone=True（退出检索但原位保留——公理 F）；
  ⑤ 未知 kind / 指向不存在条目的事件 → 忽略（前向兼容，不崩）；
  ⑥ **形态词汇两认**（W2-N3）：`entry_append`/`retrieve_hit`（重装形态）与
     `memory_append`/`memory_retrieve_hit`（融合形态 + memsys 宿主桥）投影等价。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from evocore import project_entries  # noqa: E402

TS1, TS2, TS3, TS4 = ("2026-09-23T10:00:00", "2026-09-23T11:00:00",
                      "2026-09-23T12:00:00", "2026-09-23T13:00:00")


def row(seq, kind, payload, ts):
    return (seq, ts, "llm:test", kind, __import__("json").dumps(payload, ensure_ascii=False), "p" * 64, "h" * 64)


class TestProject(unittest.TestCase):
    def test_append_creates_entry(self):
        """① 建条：id 即 entry_id。"""
        proj = project_entries([row(1, "entry_append",
                                    {"entry_id": "e1", "content": "玻璃", "content_hash": "abc"}, TS1)])
        self.assertEqual(proj["e1"]["id"], "e1")
        self.assertEqual(proj["e1"]["content"], "玻璃")
        self.assertEqual(proj["e1"]["content_hash"], "abc")

    def test_created_at_stamped_from_ledger_ts(self):
        """①b S5/T1：payload 无 created_at → 盖账本行 ts（时间原点，老化机制的前提）。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1)])
        self.assertEqual(proj["e1"]["created_at"], TS1)
        proj2 = project_entries([row(1, "entry_append",
                                      {"entry_id": "e2", "content": "x", "created_at": "2020-01-01T00:00:00"}, TS1)])
        self.assertEqual(proj2["e2"]["created_at"], "2020-01-01T00:00:00")     # 显式值优先

    def test_promotion_sets_state(self):
        """② 晋升改态。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1),
                                row(2, "promotion", {"entry_id": "e1"}, TS2)])
        self.assertEqual(proj["e1"]["state"], "longterm")

    def test_retrieve_hit_sets_last_used_from_ledger_ts(self):
        """③ 命中刷新 last_used=账本 ts（D7：持久化语义）。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1),
                                row(2, "retrieve_hit", {"entry_id": "e1", "query": "x"}, TS3)])
        self.assertEqual(proj["e1"]["last_used_at"], TS3)

    def test_tombstone_marks_kept(self):
        """④ 墓碑：标记 True 且条目**仍在投影**（原位保留）。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1),
                                row(2, "tombstone", {"entry_id": "e1", "note": "n"}, TS4)])
        self.assertTrue(proj["e1"]["tombstone"])
        self.assertIn("e1", proj)

    def test_unknown_and_orphan_ignored(self):
        """⑤ 未知 kind 与孤儿事件（指向不存在条目）→ 忽略不崩。"""
        proj = project_entries([row(1, "host_extended_kind", {"whatever": 1}, TS1),
                                row(2, "promotion", {"entry_id": "ghost"}, TS2),
                                row(3, "retrieve_hit", {"entry_id": "ghost"}, TS3),
                                row(4, "tombstone", {"entry_id": "ghost"}, TS4)])
        self.assertEqual(proj, {})

    def test_cross_form_kind_vocabulary_equivalent(self):
        """⑥ W2-N3 跨形态对拍：重装形态词汇（entry_append/retrieve_hit）与融合形态·宿主桥
        词汇（memory_append/memory_retrieve_hit）投影结果**逐字段相同**。
        负向意义：改前把投影器指向 memory_* 账本会得到 {}——与"空账本"同形，无从察觉。"""
        payload = {"entry_id": "e1", "content": "玻璃", "content_hash": "abc"}
        heavy = project_entries([row(1, "entry_append", payload, TS1),
                                 row(2, "retrieve_hit", {"entry_id": "e1"}, TS3)])
        fused = project_entries([row(1, "memory_append", payload, TS1),
                                 row(2, "memory_retrieve_hit", {"entry_id": "e1"}, TS3)])
        self.assertEqual(heavy, fused)
        self.assertEqual(fused["e1"]["last_used_at"], TS3)
        self.assertNotEqual(fused, {})            # 哨兵不裸：确认真的投出了东西

    def test_bridge_style_payload_projects(self):
        """⑥b 宿主桥真实 payload 形状（`bridge.record_append`：entry_id/content_hash/type/state，
        **无 content**）也能建条——否则指向 memsys 账本时静默投影为空。"""
        proj = project_entries([row(1, "memory_append", {
            "entry_id": "m1", "content_hash": "h" * 64,
            "type": "semantic", "state": "intermediate"}, TS1)])
        self.assertEqual(proj["m1"]["id"], "m1")
        self.assertEqual(proj["m1"]["state"], "intermediate")
        self.assertEqual(proj["m1"]["created_at"], TS1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
