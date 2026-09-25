# -*- coding: utf-8 -*-
"""entry.py — 条目形状规范（S3/T1 加法式增补：宿主写入口的构造校验面）

设计依据：《S3设计-中库规范件全量落地架构》§2.4/§四 T1——"条目构造校验"按切刀原则
（对**任意条目集合**成立）属演化内核域，故进 evocore；**本模块为纯加法**——不改动本包
现有五件一字。`STATES` 自 `.lifecycle` 引入（lifecycle 为定义处，本件为使用处，单一事实源）。
"""
from __future__ import annotations

import hashlib
import json

from .lifecycle import STATES

TYPES = ("episodic", "semantic", "procedural")


def validate_entry(e: dict) -> None:
    """条目构造校验（非法条目建不出来，P7）。非法即 raise ValueError（fail-closed）。

    规则与融合形态（evo-seat §1 `validate_entry`）**同语义**：id/content 非空 ·
    type ∈ TYPES（默认 semantic）· state ∈ STATES（默认 intermediate）· importance 非负整数。
    实现为**单一来源**（融合件与中库 CLI 共用同一套规则文本，不复制）。"""
    for k in ("id", "content"):
        if not str(e.get(k, "")).strip():
            raise ValueError(f"条目缺 {k}")
    if e.get("type", "semantic") not in TYPES:
        raise ValueError(f"type 非法：{e.get('type')!r}")
    if e.get("state", "intermediate") not in STATES:
        raise ValueError(f"state 非法：{e.get('state')!r}")
    imp = e.get("importance", 0)
    if not isinstance(imp, int) or imp < 0:
        raise ValueError(f"importance 须非负整数：{imp!r}")


def content_hash(e: dict) -> str:
    """条目内容指纹（幂等键，**64 hex**）——P3/D7 统一（20260924）。

    归一规则（**跨写入口 + 跨形态唯一来源**，SPEC §G"两个入口，一道门"）：
    排除表示形态/投影字段（id/entry_id/content_hash/state/last_used_at/**created_at**；
    state 由 importance 经 route 确定、created_at/last_used_at 由投影补齐——皆非内容），
    keywords 字符串↔词表归一为有序词表，canonical JSON 后取 sha256 全宽。
    **统一语义**：evo-seat §1 `_content_hash`（自包含镜像）与宿主桥（本函数直调）同规——
    同一逻辑条目跨三形态指纹逐位相同（`test_content_hash_divergence.py` 已转正为正向断言）。
    **去重比较＝比较时重归一**：对既有条目的投影重算本指纹再比——老库存储的旧 16 hex
    指纹不参与比较、也永不回改（append-only），故无破坏性、无迁移。
    历史：v1=16 hex 截断（S3-S4/T1 起跨写入口归一）；v2=本版（全宽+created_at 入排除集，
    关闭 `evocore-D7`）。
    """
    body = {k: v for k, v in e.items()
            if k not in ("id", "entry_id", "content_hash", "state", "last_used_at",
                         "created_at")}
    if isinstance(body.get("keywords"), str):
        body["keywords"] = sorted(body["keywords"].split())
    elif isinstance(body.get("keywords"), list):
        body["keywords"] = sorted(body["keywords"])
    canon = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
