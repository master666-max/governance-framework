# -*- coding: utf-8 -*-
"""capabilities.py — audit-kit L0：能力令牌签发与校验（v4.3 §七）
拒绝消息可机读前缀：DENY:NO_CAP / DENY:SCOPE / DENY:CANNOT / DENY:EXPIRED
"""
from __future__ import annotations

import datetime
import time

from gov_types import Capability, ResourceRef, Verdict

APPEND_EVENTS = "append_events"


def issue_capability(resource_kind: str, scope, can, cannot=(), expires=None,
                     actor: str = "human:root") -> dict:
    """签发能力：返回 kind='capability_issue' 的事件 payload（签发本身入账）。"""
    cap = Capability(resource_kind=resource_kind, scope=scope,
                     can=frozenset(can), cannot=frozenset(cannot), expires=expires)
    return {
        "kind": "capability_issue",
        "actor": actor,
        "issued_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "capability": {
            "resource_kind": cap.resource_kind,
            "scope_pattern": getattr(scope, "pattern", ""),
            "can": sorted(cap.can),
            "cannot": sorted(cap.cannot),
            "expires": cap.expires,
        },
    }


def check(cap: Capability, action: str, ref: ResourceRef,
          now: datetime.date | None = None) -> Verdict:
    """能力校验：四关全过才 ok；任一拒都带 DENY 前缀（可机读）。"""
    if now is None: now = datetime.date.today()
    if action not in cap.can:
        return Verdict("capability", False, f"DENY:NO_CAP 令牌无动作 {action!r}（can={sorted(cap.can)}）")
    if not cap.scope.matches(ref):
        return Verdict("capability", False, f"DENY:SCOPE 资源越界（{ref.resource_kind}:{ref.path}）")
    if action in cap.cannot:
        return Verdict("capability", False, f"DENY:CANNOT 动作在显式禁止列（{action!r}）")
    if cap.is_expired(now):
        return Verdict("capability", False, f"DENY:EXPIRED 令牌已于 {cap.expires} 过期")
    return Verdict("capability", True, f"action={action} ref={ref.path}")
