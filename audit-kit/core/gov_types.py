# -*- coding: utf-8 -*-
"""types.py — audit-kit L0：核心类型（非法状态不可表示——P7）
全部 frozen dataclass + __post_init__ 构造校验：非法值在构造时抛 ValueError。
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Protocol

_ACTOR_RE = re.compile(r"^(llm|fallback|human|ci):[^\s]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class ResourceRef:
    """资源引用：kind + 路径（如 ("memory", "memsys/storage/e1.json")）。"""
    resource_kind: str
    path: str

    def __post_init__(self):
        if not self.resource_kind: raise ValueError("ResourceRef.resource_kind 不可为空")
        if not self.path: raise ValueError("ResourceRef.path 不可为空")


@dataclass(frozen=True)
class Verdict:
    """门卫判定结果：ok + 可机读 detail。"""
    name: str
    ok: bool
    detail: str = ""


class Scope(Protocol):
    """作用域协议（v4.3 §七）：一切权限边界的判定面。"""
    def matches(self, ref: ResourceRef) -> bool: ...


@dataclass(frozen=True)
class PathGlobScope:
    """路径 glob 作用域（fnmatch 语义）。resource_kind 须精确相等。"""
    pattern: str
    resource_kind: str = "*"

    def __post_init__(self):
        if not self.pattern: raise ValueError("PathGlobScope.pattern 不可为空")

    def matches(self, ref: ResourceRef) -> bool:
        if self.resource_kind != "*" and self.resource_kind != ref.resource_kind:
            return False
        return fnmatch(ref.path, self.pattern)


@dataclass(frozen=True)
class Capability:
    """能力令牌（v4.3 §七）：谁能对什么资源做什么，有效期到何时。
    can/cannot 交集必须为空（构造即拒）。"""
    resource_kind: str
    scope: Scope
    can: frozenset[str]
    cannot: frozenset[str] = frozenset()
    expires: str | None = None  # 'YYYY-MM-DD'；None=永不过期（签发时慎用）

    def __post_init__(self):
        if not self.resource_kind: raise ValueError("Capability.resource_kind 不可为空")
        if not self.can: raise ValueError("Capability.can 不可为空（无能力即无令牌）")
        overlap = self.can & self.cannot
        if overlap: raise ValueError(f"can/cannot 交集非空：{sorted(overlap)}")
        if self.expires is not None:
            if not _DATE_RE.match(self.expires):
                raise ValueError(f"expires 须 YYYY-MM-DD 或 None，得 {self.expires!r}")
            try:
                datetime.date.fromisoformat(self.expires)   # 日历合法性（13 月/2 月 31 拒）
            except ValueError as e:
                raise ValueError(f"expires 非法日历日期 {self.expires!r}：{e}") from e

    def is_expired(self, now: datetime.date) -> bool:
        if self.expires is None: return False
        return now >= datetime.date.fromisoformat(self.expires)  # 当天即过期（含端点）


@dataclass(frozen=True)
class Event:
    """账本事件（v4.3 §六 events 表行的内存形态）。"""
    seq: int
    ts: str
    actor: str
    kind: str
    payload: dict
    prev_hash: str
    self_hash: str

    def __post_init__(self):
        if self.seq < 1: raise ValueError(f"seq 须 ≥1，得 {self.seq}")
        if not _ACTOR_RE.match(self.actor):
            raise ValueError(f"actor 须形如 'llm:x'|'fallback:rule'|'human:a'|'ci:hook'（类别:标识），得 {self.actor!r}")
        if not self.kind: raise ValueError("kind 不可为空")
        try:
            json.dumps(self.payload)
        except (TypeError, ValueError) as e:
            raise ValueError(f"payload 必须可 JSON 序列化：{e}") from e
        for name in ("prev_hash", "self_hash"):
            h = getattr(self, name)
            if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                raise ValueError(f"{name} 须 64 位小写十六进制，得 {h[:16]}…")
