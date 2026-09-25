# -*- coding: utf-8 -*-
"""bridge.py — W4：memsys 引擎接入 audit-kit 账本（v4.3 §五"治理机器一行不重写"）
引擎的每次写入/决策/生命周期事件 → audit-kit events 账本（kind 注册表见 memsys/kinds.yml）。
memsys 侧只依赖 audit-kit 公开面（Ledger.append + Capability），反向零依赖（P9）。
"""
from __future__ import annotations

import datetime
import os
import sys

_MEMSYS = os.path.dirname(os.path.abspath(__file__))          # memsys/
_ROOT = os.path.normpath(os.path.join(_MEMSYS, ".."))         # 仓根（evocore **包导入**用——entry 有包内相对导入，平铺导入会炸）
_AUDKIT = os.path.normpath(os.path.join(_MEMSYS, "..", "audit-kit"))
for sub in ("core", "ledger", "engine"):
    for base in (_AUDKIT, _MEMSYS):
        p = os.path.normpath(os.path.join(base, sub))
        if os.path.isdir(p) and p not in sys.path: sys.path.insert(0, p)
if _ROOT not in sys.path: sys.path.insert(0, _ROOT)           # P3/D7：指纹唯一来源（包导入）

from gov_types import Capability, PathGlobScope   # noqa: E402  (audit-kit L0)
from ledger import Ledger                         # noqa: E402  (audit-kit L1)
from evocore.entry import content_hash            # noqa: E402  (evocore 演化机制·统一指纹)

# memsys 写入能力：记忆域资源 + append_events（scope=表级，触发器物理兜底）
MEMSYS_CAP = Capability(
    resource_kind="memory",
    scope=PathGlobScope("events", "table"),
    can=frozenset({"append_events"}),
    expires=None,  # 宿主常设能力；撤销走 capability_revoke
)

# kind 注册表（与 memsys/kinds.yml 对齐；宿主注册，框架开放集）
KINDS = ("memory_adjudicate", "human_override", "promotion", "attic_nomination",
         "memory_append", "memory_retrieve_hit", "tombstone")


class MemoryLedger:
    """memsys→audit-kit 的账本桥。引擎侧唯一调用面。"""

    def __init__(self, db_path: str):
        self._led = Ledger.open(db_path)

    def record_append(self, actor: str, entry_id: str, entry: dict) -> dict:
        """条目写入留痕：kind=memory_append（含 content_hash 幂等键）。

        P3/D7 统一（20260924）：指纹改用 evocore 唯一来源 `content_hash`（64 hex·归一）——
        原内联"全量 entry 64 hex 无排除无归一"是三口径分歧的第三叉，随统一关闭。
        """
        chash = content_hash(entry)
        return self._led.append(MEMSYS_CAP, actor, "memory_append", {
            "entry_id": entry_id, "content_hash": chash,
            "type": entry.get("type", "semantic"), "state": entry.get("state", "intermediate"),
        })

    def record_decision(self, actor: str, trace: dict) -> dict:
        """决策留痕（decision.adjudicate_* 的返回值直接入账）。"""
        return self._led.append(MEMSYS_CAP, actor, "memory_adjudicate", trace)

    def record_lifecycle(self, actor: str, ev: dict) -> dict:
        """生命周期事件（promotion/attic_nomination/tombstone）。"""
        kind = ev.get("kind", "promotion")
        if kind not in KINDS:
            raise ValueError(f"未注册 kind：{kind}")
        return self._led.append(MEMSYS_CAP, actor, kind, ev)

    def record_hit(self, actor: str, entry_id: str, query: str) -> dict:
        """检索命中留痕（last_used 刷新的账面依据）。"""
        return self._led.append(MEMSYS_CAP, actor, "memory_retrieve_hit", {
            "entry_id": entry_id, "query": query[:120],
        })

    def head(self) -> str: return self._led.head()
    def count(self) -> int: return self._led.count()
    def close(self) -> None: self._led.close()
