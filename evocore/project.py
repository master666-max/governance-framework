# -*- coding: utf-8 -*-
"""project.py — 事件流→条目集投影（S4/T1 加法式增补：**单一投影器**）

设计依据：《S4设计-L2-0服务件全量落地架构》§2.3 裁定①——server 与 kb CLI 必须共用
同一投影器（"两个投影器必然漂移"属 D7/D8 同类隐患，事前处置）。本模块为纯加法：
不改动本包其余模块一字。

投影语义（S5/T1 对齐：与融合件 §7 `_load_entries` **同语义**——形态分离、语义对齐）：
  entry_append → 建条（含 content_hash；id=entry_id；**created_at=payload 显式值，否则账本行 ts**）
  promotion    → state=longterm
  retrieve_hit → last_used_at=账本行 ts（**D7 登记项**：中库/服务形态按语义实现持久化；
                 融合件 evo-seat 的 touch 仅内存态——触发器=融合件版本周期对齐）
  tombstone    → tombstone=True（退出检索，原位保留——公理 F）
"""
from __future__ import annotations

import json

# 形态词汇**两认**（W2-N3 · 20260923 开工批）：同一语义在两种形态里有两套 kind 名——
#   融合形态（`evo_seat.py` §7 `_load_entries`）与 memsys 宿主桥（`bridge.record_append`）
#     写 `memory_append` / `memory_retrieve_hit`；
#   重装形态（中库 `kb.py` CLI / L2 `server.py`）写 `entry_append` / `retrieve_hit`。
# 只认一套的后果：把投影器指向另一套写出的账本时**静默投影为空**——而"未知 kind 忽略"
# 本是前向兼容特性，于是「没投出东西」与「账本本来就空」在输出上同形（第一定理）。
# 两认不新增任何行为：语义同一，只是不再因形态词汇差异而丢账。
APPEND_KINDS = ("entry_append", "memory_append")
HIT_KINDS = ("retrieve_hit", "memory_retrieve_hit")


def project_entries(rows) -> dict:
    """把账本行序列投影为条目集 {entry_id: entry}。

    rows 形态=账本 `.rows()` 的产出：
      (seq, ts, actor, kind, payload, prev_hash, self_hash)
    未知 kind 忽略（前向兼容：账本可含宿主扩展 kind）。
    """
    proj = {}
    for _seq, ts, _actor, kind, payload, _ph, _sh in rows:
        p = json.loads(payload)
        if kind in APPEND_KINDS:
            e = {**p, "id": p["entry_id"]}
            if not e.get("created_at"):
                e["created_at"] = ts      # S5/T1：时间原点=账本行 ts（payload 显式值优先）
            proj[p["entry_id"]] = e
        elif kind == "promotion" and p.get("entry_id") in proj:
            proj[p["entry_id"]]["state"] = "longterm"
        elif kind in HIT_KINDS and p.get("entry_id") in proj:
            proj[p["entry_id"]]["last_used_at"] = ts
        elif kind == "tombstone" and p.get("entry_id") in proj:
            proj[p["entry_id"]]["tombstone"] = True
    return proj


OVERRIDE_KIND = "human_override"


def project_overrides(rows) -> list:
    """人侧终裁事件投影（S8-4 · 20260923 开工批）：`[(自身 seq, payload)]`。

    与融合形态 `evo_seat.py` §7 `_overrides` **同语义**（形态分离、语义对齐）。
    终裁不删历史——被终裁的判定事件仍在账；本函数只把终裁取出来供读侧标注。
    payload 冻结（S8工单 S8-4）：`{target_seq?, decision, rationale, cap_ref?}`。
    """
    out = []
    for seq, _ts, _actor, kind, payload, _ph, _sh in rows:
        if kind == OVERRIDE_KIND:
            out.append((seq, json.loads(payload)))
    return out


def project_sources(rows) -> dict:
    """来源视图投影（S8-6 最小版）：`{actor: {events, by_kind, last_ts}}`。

    只回答一个问题——「**谁的 Agent 在喂什么**」：按 actor 聚合事件数、按 kind 的分布、
    最近一次时间。**不判可信度、不计算被采纳率/污染率**（那属完整版，归 L2-2；
    见 `裁定索引.md` §一 第 13 行）。

    **与工单字面的一处偏离（登记在此）**：S8工单 S8-6 写的是「按 `actor` 前缀聚合」，
    本实现按**完整 actor** 聚合。理由：L2 的 actor 规约是 `llm:<平台>:<grant_id>`，
    截第一段会把 `llm:alpha:g1` 与 `llm:beta:g2` 并进同一个 `llm` 桶——
    而那恰恰是本视图唯一要区分的东西（本批实跑服务件时抓到：两身份各写 1 条，
    截前缀后显示成"llm 2 条"，视图形同失效）。要家族级汇总，对键再切一次即可。
    与融合形态 `evo_seat.py` §7 `_source_stats` 同语义（跨形态一致性由
    `build/tests/test_sources_view.py` 钉，不靠注释声称）。
    """
    out: dict = {}
    for _seq, ts, actor, kind, _payload, _ph, _sh in rows:
        key = actor or "(空 actor)"
        s = out.setdefault(key, {"events": 0, "by_kind": {}, "last_ts": ""})
        s["events"] += 1
        s["by_kind"][kind] = s["by_kind"].get(kind, 0) + 1
        if ts > s["last_ts"]:
            s["last_ts"] = ts
    return out


def override_marks(rows) -> dict:
    """把终裁回溯到条目：`payload.target_seq` → 该 seq 的判定留痕里的 `entries[]`。

    返回 `{entry_id: [(终裁自身 seq, 被终裁的判定 seq, decision, rationale)]}`；
    无 `target_seq` 的方针性终裁不入此表。与融合件 `_override_marks` 同语义。
    """
    materialized = [(seq, ts, actor, kind, payload, ph, sh)
                    for seq, ts, actor, kind, payload, ph, sh in rows]
    adj = {}
    for seq, _ts, _actor, kind, payload, _ph, _sh in materialized:
        if kind == "memory_adjudicate":
            adj[seq] = json.loads(payload).get("entries", [])
    marks = {}
    for ov_seq, p in project_overrides(materialized):
        tgt = p.get("target_seq")
        if tgt is None:
            continue
        try:
            tseq = int(tgt)
        except (TypeError, ValueError):
            continue   # 畸形 target_seq：跳过而非中断整表
        for eid in adj.get(tseq, []):
            marks.setdefault(eid, []).append((ov_seq, tseq, p.get("decision"), p.get("rationale")))
    return marks
