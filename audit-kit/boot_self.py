# -*- coding: utf-8 -*-
"""boot_self.py — W3 自举：audit-kit 用自己的账本记自己的提交（v4.3 §4.4）
只读 git 历史 + 写自举账本（audit-kit/state/boot.db，已 gitignore）。
用法（在审计区根目录下）:
  py -X utf8 audit-kit/boot_self.py --sync     # 把 git 提交史同步进账本（幂等）
  py -X utf8 audit-kit/boot_self.py --status   # 账本状态+与 git 的对照
  py -X utf8 audit-kit/boot_self.py --rebuild  # 老算法库（hash v1）重建为 v2；原库改名留档，不删除
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("core", "ledger"):
    p = os.path.normpath(os.path.join(_HERE, sub))
    if p not in sys.path: sys.path.insert(0, p)

from gov_types import Capability, PathGlobScope  # noqa: E402
from ledger import Ledger, LedgerError           # noqa: E402

AUD = os.path.normpath(os.path.join(_HERE, ".."))
DB = os.path.join(_HERE, "state", "boot.db")

# 自举能力：CI 对本仓 events 表的追加权（scope=表级；触发器已物理兜底）
BOOT_CAP = Capability(
    resource_kind="table",
    scope=PathGlobScope("events", "table"),
    can=frozenset({"append_events"}),
    expires=None,  # 自举常设；撤销走 capability_revoke 事件
)


def git_log() -> list[dict]:
    r = subprocess.run(
        ["git", "-C", AUD, "log", "--reverse", "--format=%H%x1f%ad%x1f%an%x1f%s",
         "--date=format:%Y-%m-%dT%H:%M:%S"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"git log 失败：{r.stderr[:200]}")
    out = []
    for line in r.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            out.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3][:200]})
    return out


def recorded_hashes(led: Ledger) -> tuple[set[str], int]:
    """返回 (已入账 commit 集, 坏行数)。payload 非法 json 属异常——fail-closed 计数上报，不吞。"""
    import json
    got: set[str] = set()
    bad = 0
    for _seq, _ts, _actor, _kind, payload, *_ in led.rows():
        try:
            got.add(json.loads(payload).get("commit", ""))
        except Exception:
            bad += 1
    return got, bad


def cmd_sync() -> None:
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    led = Ledger.open(DB)
    have, bad = recorded_hashes(led)
    if bad:
        print(f"⚠ 账本含 {bad} 条无法解析的 payload（fail-closed：请人工核查）")
    commits = git_log()
    new = [c for c in commits if c["hash"] not in have]
    for c in new:
        led.append(BOOT_CAP, "ci:boot-self", "governance_change", {
            "what": "audit-kit 自举：提交入账",
            "commit": c["hash"], "author": c["author"], "subject": c["subject"],
        })
    led.close()
    print(f"自举同步：git 提交 {len(commits)}，账本已有 {len(have)}，本次新增 {len(new)}")


def cmd_rebuild() -> None:
    """老算法库（hash v1）重建为 v2。

    正当性（写下来防被当"抹账"）：boot.db 是 **git 提交史的可复算投影**——真源是 git，
    账本只是它的索引；且该库在 .gitignore 内（`audit-kit/state/`），不入版本库。
    纪律：**不删除**——原库改名留档（`boot.db.pre-v2.bak`），拒绝覆盖既有备份。
    """
    if not os.path.isfile(DB):
        print("自举账本不存在——直接 --sync 即可（无需重建）")
        return
    bak = DB + ".pre-v2.bak"
    if os.path.exists(bak):
        raise SystemExit(f"备份已存在（{bak}）——先人工处置，拒绝覆盖（fail-closed）")
    old_size = os.path.getsize(DB)
    os.replace(DB, bak)
    print(f"原库改名留档：{bak}（{old_size} B，未删除）")
    cmd_sync()
    print("重建完成：新库以 hash v2 写入（actor/kind 并入哈希输入）；"
          "旧库内容可从 .bak 只读比对")


def cmd_status() -> None:
    if not os.path.isfile(DB):
        print("自举账本不存在（先 --sync）"); return
    led = Ledger.open(DB)  # 开库即验：链+触发器
    have, bad = recorded_hashes(led)
    if bad:
        print(f"⚠ 账本含 {bad} 条无法解析的 payload（fail-closed：请人工核查）")
    commits = git_log()
    missing = [c["hash"][:8] for c in commits if c["hash"] not in have]
    extra = have - {c["hash"] for c in commits}
    print(f"账本事件 {led.count()}；链头 {led.head()[:16]}…")
    print(f"git 提交 {len(commits)}；账本覆盖 {len(have)}；缺失 {len(missing)}"
          + (f"（如 {missing[:3]}）" if missing else " ✓ 全覆盖"))
    if extra:
        print(f"⚠ 账本含 git 之外的 commit 引用 {len(extra)} 个")
    led.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="老算法库（hash v1）重建为 v2：原库改名留档（不删除）后按 git 史重放")
    a = ap.parse_args()
    if a.rebuild: cmd_rebuild()
    elif a.sync: cmd_sync()
    elif a.status: cmd_status()
    else: ap.print_help(); raise SystemExit(2)


if __name__ == "__main__":
    main()
