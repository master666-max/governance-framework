# -*- coding: utf-8 -*-
"""hashes.py — audit-kit L0：链式哈希（纯函数，零依赖）
契约（v4.3 §六）：self_hash = sha256(prev_hash || canonical_json(payload))
"""
import hashlib
import json

GENESIS = "0" * 64  # 链首 prev（64 个 0）

# 事件哈希算法版本（W2-N2 · 20260923）：入库登记于 meta.hash_algo，开库即验。
# v1=只覆盖 payload（改 actor/kind 重放漏检）；v2=actor/kind 并入输入。
# 换代属破坏性变更：老算法库**拒读**（不静默重算、不误报篡改），重建路径见 boot_self.py --rebuild。
HASH_ALGO = "v2"

def canonical_json(obj) -> str:
    """规范 JSON：键排序、无空白、保 unicode——同一 payload 恒同一字节串。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def event_hash(prev_hash: str, payload, actor: str = "", kind: str = "") -> str:
    """事件哈希 v2（20260923 评审采纳）：actor/kind 并入哈希输入——头部字段
    篡改可检出（v1 只覆盖 payload，改 actor/kind 重放漏检，评审复现 CONFIRMED）。
    ts 不并入（DB 默认值时序决定，写入时刻由链序+开库验证覆盖）；seq 由链位置保证。"""
    if len(prev_hash) != 64 or any(c not in "0123456789abcdef" for c in prev_hash):
        raise ValueError(f"prev_hash 须 64 位小写十六进制，得：{prev_hash[:16]}…")
    body = canonical_json({"actor": actor, "kind": kind, "payload": payload})
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()

def genesis_prev() -> str:
    """链首 prev（genesis）。"""
    return GENESIS
