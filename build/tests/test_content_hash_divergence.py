# -*- coding: utf-8 -*-
"""test_content_hash_divergence.py — 三形态 content_hash **统一后的正向断言**（P3 · 20260924）

沿革（缺陷登记 `evocore-D7` → 本件转正）：
  本件原为"三口径分歧"的钉桩（16/16/64 · 归一/不归一/无归一，两两不同）。
  P3 波（预注册-三件推进·20260924）按版本闸完成统一——**三形态同规则、同指纹**：
  ① `evocore/entry.py:content_hash`   **64 hex** · 排除 id/entry_id/content_hash/
     state/last_used_at/**created_at** · keywords 归一有序词表（唯一来源）
  ② `evo-seat/evo_seat.py:_content_hash`  同规则**自包含镜像**（本件自包含约束）
  ③ `memsys/bridge.py:record_append`      直调 ①（不再内联算法）
  ⇒ 同一逻辑条目跨三形态指纹**逐位相同**，跨形态迁移幂等去重成立（SPEC §G）。
  去重比较＝**比较时重归一**：老库存量 16 hex 指纹不参与比较、永不回改（无破坏性迁移）。

用法: py -X utf8 build/tests/test_content_hash_divergence.py
"""
import importlib.util
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from evocore.entry import content_hash as canon_hash   # noqa: E402  ①唯一来源


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_seat = _load("_w2_seat", os.path.join("evo-seat", "evo_seat.py"))
fused_hash = _seat._content_hash                      # noqa: E402  ②融合形态（镜像）

# 探针条目：故意带上全部投影/表示形态字段（created_at/state/last_used_at/keywords 字符串）
PROBE = {"entry_id": "e1", "id": "e1", "content": "玻璃 IOR 1.45",
         "keywords": "玻璃 ior", "importance": 3,
         "created_at": "2026-09-23T10:00:00",
         "state": "intermediate", "last_used_at": "2026-09-23T10:00:00"}


def _bridge_hash(entry):
    """③宿主桥口径：走真实写账路径取回 content_hash（不复制算法，防断言自身漂移）。"""
    bridge = _load("_w2_bridge", os.path.join("memsys", "bridge.py"))
    db = os.path.join(tempfile.mkdtemp(), "w2n4.db")
    led = bridge.MemoryLedger(db)
    try:
        row = led.record_append("test:w2n4", entry["entry_id"], entry)
        return row["payload"]["content_hash"]
    finally:
        led._led.close()


class TestContentHashUnified(unittest.TestCase):
    def test_three_impls_identical(self):
        """P3 核心：三套实现（唯一来源/融合镜像/宿主桥直调）对同一探针**逐位相同**。"""
        c, f, b = canon_hash(PROBE), fused_hash(PROBE), _bridge_hash(PROBE)
        self.assertEqual(c, f, f"①唯一来源 vs ②融合镜像 不同 ⇒ 镜像漂移（c={c[:12]} f={f[:12]}）")
        self.assertEqual(c, b, f"①唯一来源 vs ③宿主桥 不同 ⇒ 桥未走唯一来源（c={c[:12]} b={b[:12]}）")

    def test_width_unified_64(self):
        """统一宽度 = 64 hex 全宽（v1 的 16 截断退役）。"""
        for name, fn in (("①canon", canon_hash), ("②fused", fused_hash), ("③bridge", _bridge_hash)):
            h = fn(PROBE)
            self.assertEqual(len(h), 64, f"{name} 宽度 {len(h)} ≠ 64")

    def test_each_impl_deterministic(self):
        """三套各自确定性（同输入同输出）。"""
        for name, fn in (("①canon", canon_hash), ("②fused", fused_hash), ("③bridge", _bridge_hash)):
            self.assertEqual(fn(PROBE), fn(dict(PROBE)), f"{name} 不确定")

    def test_all_ignore_projection_fields(self):
        """统一性质：state/last_used_at/created_at 属表示形态/投影字段——改它们不改指纹。"""
        moved = {**PROBE, "state": "longterm",
                 "last_used_at": "2030-01-01T00:00:00",
                 "created_at": "2020-01-01T00:00:00"}
        for name, fn in (("①canon", canon_hash), ("②fused", fused_hash), ("③bridge", _bridge_hash)):
            self.assertEqual(fn(PROBE), fn(moved), f"{name} 对投影字段敏感（归一失守）")

    def test_all_normalize_keywords(self):
        """统一性质：keywords 字符串 ↔ 词表 且乱序 → 同指纹（三套齐备）。"""
        a = {**PROBE, "keywords": "玻璃 ior"}
        b = {**PROBE, "keywords": ["ior", "玻璃"]}
        for name, fn in (("①canon", canon_hash), ("②fused", fused_hash), ("③bridge", _bridge_hash)):
            self.assertEqual(fn(a), fn(b), f"{name} keywords 未归一")

    def test_different_content_still_differs(self):
        """判别力对照：统一≠弱化——不同内容必不同指纹（防"统一成常量"式假通过）。"""
        other = {**PROBE, "content": "完全不同的内容"}
        for name, fn in (("①canon", canon_hash), ("②fused", fused_hash), ("③bridge", _bridge_hash)):
            self.assertNotEqual(fn(PROBE), fn(other), f"{name} 对不同内容同指纹")

    def test_unification_is_registered(self):
        """登记闭合：D7 关闭须同步更新 `evocore/README.md`（行在+标记统一）。"""
        readme = open(os.path.join(ROOT, "evocore", "README.md"), encoding="utf-8").read()
        self.assertIn("D7", readme, "evocore/README.md 债务表应保留 D7 行（标注已统一）")
        self.assertIn("统一", readme, "D7 行未标注统一态")


if __name__ == "__main__":
    unittest.main(verbosity=2)
