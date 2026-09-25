# -*- coding: utf-8 -*-
"""ledger.py — audit-kit L1：events 单库即真相（v4.3 §六）
SQLite + 触发器物理 append-only + 链式哈希重放验证 + 能力校验内嵌写入。
单写者纪律：每库一个写连接（W-4 锁语义后续期接入；当前 open() 即占写权）。
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

import sys
_CORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core")
if _CORE not in sys.path: sys.path.insert(0, _CORE)

from gov_types import Capability, Event, ResourceRef  # noqa: E402
from hashes import event_hash, genesis_prev, HASH_ALGO  # noqa: E402
from capabilities import check, APPEND_EVENTS         # noqa: E402

_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


class LedgerError(Exception):
    """账本层一切失败（fail-closed：越权/链断/触发器缺失/库损坏）。"""


def _missing_triggers(conn: sqlite3.Connection) -> set:
    """触发器在位核对（S2-T2 去重）：开库先验与链验证共用同一读取实现。
    两处错文保留各自表述（open=既有库拒重建；verify=未物理强制）——语义面零改。"""
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'")}
    return {"no_update", "no_delete"} - names


class Ledger:
    """events 账本。唯一写入口 append(cap, actor, kind, payload)。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ---- 开库 ----
    @classmethod
    def open(cls, path: str) -> "Ledger":
        """建库（幂等）+ 立即验证（链+触发器）。任何不一致 raise LedgerError。
        顺序敏感：既有库先验触发器再 executescript——否则 IF NOT EXISTS 会把
        被摘除的触发器静默重建，掩盖破坏（test_missing_trigger 抓出的 bug）。"""
        if not os.path.isfile(_SCHEMA_PATH):
            raise LedgerError(f"schema.sql 缺失：{_SCHEMA_PATH}")
        preexisting = os.path.isfile(path)
        conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")  # W-4：并发写者排队而非立即 SQLITE_BUSY
        if preexisting:
            cls._require_triggers(conn)   # 既有库：先验，验不过不许建（fail-closed）
            cls._require_hash_algo(conn)  # 老算法库先拒（防 SCHEMA 补键掩盖——融合形态同族教训）
        try:
            with open(_SCHEMA_PATH, encoding="utf-8") as f:
                conn.executescript(f.read())
        except sqlite3.Error as e:
            raise LedgerError(f"schema 执行失败：{e}") from e
        led = cls(conn)
        led.verify()  # 链重放（开库即验：坏库不许用）
        return led

    @staticmethod
    def _require_hash_algo(conn: sqlite3.Connection) -> None:
        """事件哈希算法版本闸（W2-N2 · 20260923）。

        病灶：v2 把 actor/kind 并入哈希输入后，v1 写入的老库在 verify() 里报
        「哈希不符 seq=1（疑似篡改）」——把**算法换代误报成篡改**，读者无从区分。
        本闸在开库时先判算法代：**缺键不误杀**（首行试算自动识别——v2 命中即在途库，
        补键放行；试算不中即 v1 或损坏，拒读并给重建路径）。
        与融合形态 `evo_seat.py` §2 `_require_hash_algo` 同族同语义（形态分离、语义对齐）。
        """
        has_events = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        if not has_events:
            return                        # 空库/未初始化：无算法代可判
        has_meta = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        row = conn.execute("SELECT v FROM meta WHERE k='hash_algo'").fetchone() if has_meta else None
        if row and row[0] == HASH_ALGO:
            return                        # 已登记同代：放行
        first = conn.execute(
            "SELECT actor, kind, prev_hash, payload, self_hash FROM events ORDER BY seq LIMIT 1").fetchone()
        if not first:
            return                        # 有表无行：无判定材料
        try:
            hit = event_hash(first[2], json.loads(first[3]), first[0], first[1]) == first[4]
        except (ValueError, TypeError):
            hit = False
        if hit:
            if has_meta:                  # 在途 v2 库（键缺失晚于算法切换）：补键放行
                conn.execute("INSERT OR IGNORE INTO meta (k, v) VALUES ('hash_algo', ?)", (HASH_ALGO,))
            return                        # 无 meta 表时不建表——随后的 executescript 会补键
        raise LedgerError(
            f"老库（事件哈希算法 {(row[0] if row else 'v1')} ≠ 现版 {HASH_ALGO}）：不可读。"
            f"v2 起 actor/kind 并入哈希输入（破坏性变更）——本库为换代前写入，"
            f"不是篡改；重建路径见 `boot_self.py --rebuild`（原库改名留档，不删除）")

    @staticmethod
    def _require_triggers(conn: sqlite3.Connection) -> None:
        has_events = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        if not has_events:
            return  # 空库/未初始化：无触发器是正常态
        missing = _missing_triggers(conn)
        if missing:
            raise LedgerError(
                f"既有库触发器缺失（append-only 被破坏，拒绝静默重建）：{sorted(missing)}")

    def close(self) -> None:
        self._conn.close()

    # ---- 验证 ----
    def verify(self) -> None:
        """链重放 + 触发器在位。任何不一致 raise LedgerError。"""
        missing = _missing_triggers(self._conn)
        if missing:
            raise LedgerError(f"触发器缺失（append-only 未物理强制）：{sorted(missing)}")
        prev = genesis_prev()
        for seq, row_actor, row_kind, row_prev, payload, self_h in self._conn.execute(
                "SELECT seq, actor, kind, prev_hash, payload, self_hash FROM events ORDER BY seq"):
            if row_prev != prev:
                raise LedgerError(f"链断裂 seq={seq}：prev_hash 不衔接（期望 {prev[:12]}… 得 {row_prev[:12]}…）")
            try:
                recomputed = event_hash(prev, json.loads(payload), row_actor, row_kind)
            except Exception as e:  # json 解析失败或哈希计算失败：一律判不可复算
                raise LedgerError(f"seq={seq} 事件不可复算：{e}") from e
            if recomputed != self_h:
                raise LedgerError(f"哈希不符 seq={seq}：期望 {recomputed[:12]}… 得 {self_h[:12]}…（疑似篡改，含头部字段）")
            prev = self_h

    def _last_hash(self) -> str:
        """链尾哈希（S2-T2 去重）：append 取 prev 与 head 共用。"""
        row = self._conn.execute(
            "SELECT self_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else genesis_prev()

    # ---- 写入（唯一入口） ----
    def append(self, cap: Capability, actor: str, kind: str, payload: dict) -> dict:
        """能力校验 → 链尾衔接 → INSERT → 返回该行。越权在插入前被拒。"""
        ref = ResourceRef("table", "events")
        verdict = check(cap, APPEND_EVENTS, ref)
        if not verdict.ok:
            raise LedgerError(verdict.detail)  # DENY 前缀透传，可机读
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as e:
            raise LedgerError(f"payload 不可序列化：{e}") from e
        # W-4：取尾→INSERT 同一事务（BEGIN IMMEDIATE 串行化并发写者）；
        # 分离执行会令两写者同读尾哈希→链分叉，而触发器禁修（不可恢复）。
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            prev = self._last_hash()
            self_h = event_hash(prev, payload, actor, kind)
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            cur = self._conn.execute(
                "INSERT INTO events (ts, actor, kind, payload, prev_hash, self_hash) "
                "VALUES (?,?,?,?,?,?)", (ts, actor, kind, payload_json, prev, self_h))
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return {"seq": cur.lastrowid, "ts": ts, "actor": actor, "kind": kind,
                "payload": payload, "prev_hash": prev, "self_hash": self_h}

    # ---- 只读面 ----
    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def head(self) -> str:
        return self._last_hash()

    def rows(self):
        for r in self._conn.execute(
                "SELECT seq, ts, actor, kind, payload, prev_hash, self_hash "
                "FROM events ORDER BY seq"):
            yield r
