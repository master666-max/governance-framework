# -*- coding: utf-8 -*-
"""tools_crosscheck.py — 双包对拍：audit-kit × memsys 合并后仍守 v4.3 双包不变量
用法（在仓库根目录）: py -X utf8 audit-kit/tools_crosscheck.py   （无参数；-h 看说明）
三项检查各输出一行 [PASS]/[FAIL]；全过 exit 0，任一 FAIL exit 1：
  1. 双库同链：同一 SQLite 先 audit-kit 侧 append、再 memsys 侧（经 bridge）append，
     链自 genesis 起无缝衔接（head 逐级递进 + 重开重放 verify 通过）——两包一条真相链。
  2. 隔离面：ast 扫描 audit-kit/ 全部 .py 的 import，不得出现任何 memsys 符号
     （P9：框架不知道宿主）；违例输出 文件:行号。本工具自身是跨包审计件，
     豁免方式=精确自身路径（非目录豁免，防豁免面被滥用）。
  3. kind 注册一致性：bridge.KINDS 每个 kind 都在 memsys/kinds.yml 有声明
     （防 F3：同一事实两套声明漂移）。方向单向 KINDS⊆yml：yml 是宿主开放集，
     宿主扩展 kind 多声明不罚。
零第三方依赖；路径一律由 __file__ 推导，禁绝对路径硬编码。
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))             # tools/
_ROOT = os.path.dirname(_HERE)                                 # 工作区根
_AUDKIT = os.path.join(_ROOT, "audit-kit")                     # 20260925 迁入 tools/：core/ledger 归位 audit-kit 显式推导
_MEMSYS = os.path.join(_ROOT, "memsys")
for p in (os.path.join(_AUDKIT, "core"), os.path.join(_AUDKIT, "ledger"), _MEMSYS):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from gov_types import Capability, PathGlobScope   # noqa: E402  (audit-kit L0)
from hashes import genesis_prev                   # noqa: E402  (audit-kit L0)
from ledger import Ledger                         # noqa: E402  (audit-kit L1)
from bridge import KINDS, MemoryLedger            # noqa: E402  (memsys 宿主桥)

KINDS_YML = os.path.join(_MEMSYS, "kinds.yml")

# P9 隔离面禁入符号：宿主/内核侧包名 + 注入式裸模块名（本仓 sys.path 注入惯用法，
# 宿主/内核模块在 audit-kit 侧将以此形态出现）+ 桥公开类/常量名。
# S1 后：tunables/retrieval/lifecycle/decision 的实体已从 memsys/engine 平移至
# evocore（新增禁用符号 "evocore"）；"engine" 已无实体，保留作**陈旧布局绊线**
# （此后任何 `import engine` 都是过期引用，应被抓）。
MEMSYS_SURFACE = frozenset({
    "memsys", "bridge", "engine", "evocore", "tunables", "retrieval", "lifecycle",
    "decision", "MemoryLedger", "MEMSYS_CAP",
})

_KIND_LINE = re.compile(r"^ {2}([A-Za-z_][A-Za-z0-9_]*):\s*$")   # kinds.yml 的 kind 声明行


def check_dual_chain(workdir: str) -> tuple[bool, str]:
    """不变量①：同一 SQLite 两包接力写，链自 genesis 无缝衔接且重放通过。"""
    db = os.path.join(workdir, "crosscheck.db")
    cap = Capability("memory", PathGlobScope("*", "table"),
                     frozenset({"append_events"}), frozenset(), "2099-12-31")
    led = Ledger.open(db)                                # audit-kit 侧写第一环
    r1 = led.append(cap, "ci:crosscheck", "anchor", {"side": "audit-kit"})
    ok_genesis = r1["prev_hash"] == genesis_prev()       # 链首接 genesis
    ok_head1 = led.head() == r1["self_hash"]             # head 递进至本环
    led.close()                                          # 单写者纪律：换边先交写权
    mled = MemoryLedger(db)                              # memsys 侧（经 bridge）接第二环
    r2 = mled.record_append("llm:crosscheck", "e-cross", {"content": "双包对拍"})
    ok_link = r2["prev_hash"] == r1["self_hash"]         # 跨包衔接：宿主环接框架环
    ok_head2 = mled.head() == r2["self_hash"]
    mled.close()
    led2 = Ledger.open(db)                               # 重开=链重放+触发器在位
    ok_replay = led2.count() == 2 and led2.head() == r2["self_hash"]
    led2.close()
    ok = ok_genesis and ok_head1 and ok_link and ok_head2 and ok_replay
    detail = (f"genesis_ok={ok_genesis} head1_ok={ok_head1} link_ok={ok_link} "
              f"head2_ok={ok_head2} replay_ok={ok_replay}（seq1={r1['seq']}, seq2={r2['seq']}）")
    return ok, detail


def _memsys_import_violations(tree: ast.AST, path: str) -> list:
    """收集单文件 import 里的 memsys 禁入符号，报 文件:行号。相对导入出不了本包，不查。"""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in MEMSYS_SURFACE:
                    hits.append(f"{path}:{node.lineno} import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue
            if node.module and node.module.split(".")[0] in MEMSYS_SURFACE:
                hits.append(f"{path}:{node.lineno} from {node.module} import …")
            for a in node.names:
                if a.name in MEMSYS_SURFACE:
                    hits.append(f"{path}:{node.lineno} from … import {a.name}")
    return hits


def check_isolation(auditkit_root: str) -> tuple[bool, str]:
    """不变量②：audit-kit 下全部 .py 的 import 无 memsys 符号（P9 框架不知道宿主）。"""
    me = os.path.abspath(__file__)
    hits = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(auditkit_root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.abspath(os.path.join(dirpath, fn))
            if full == me:
                continue                                 # 本工具=跨包审计件，精确自豁免
            scanned += 1
            try:
                with open(full, encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            except (OSError, SyntaxError, ValueError) as e:
                hits.append(f"{full}:? 解析失败（fail-closed）：{e}")
                continue
            hits.extend(_memsys_import_violations(tree, full))
    detail = f"scanned={scanned}；" + ("; ".join(hits) if hits else "无 memsys 符号 ✓")
    return (not hits), detail


def _kinds_from_yml(text: str) -> set:
    """stdlib 极简解析 kinds.yml：只认顶层 kinds: 块下 2 空格缩进的 `name:` 行
    （描述文本/更深缩进里出现同名不算声明——防子串误判）。"""
    names = set()
    in_kinds = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[0].isspace():                        # 顶层键：kinds: 开块，其余闭块
            in_kinds = line.rstrip() == "kinds:"
            continue
        m = _KIND_LINE.match(line)
        if in_kinds and m:
            names.add(m.group(1))
    return names


def check_kinds(yml_path: str) -> tuple[bool, str]:
    """不变量③：bridge.KINDS ⊆ kinds.yml 声明（防 F3 两套声明漂移；缺一即拒）。"""
    with open(yml_path, encoding="utf-8") as f:
        yml_kinds = _kinds_from_yml(f.read())
    missing = [k for k in KINDS if k not in yml_kinds]
    detail = (f"bridge.KINDS={len(KINDS)} yml声明={len(yml_kinds)}；"
              + (f"缺失 {missing}" if missing else "无漂移 ✓（yml 可含宿主扩展，开放集）"))
    return (not missing), detail


def main() -> int:
    """三项检查各打一行 [PASS]/[FAIL]；全过 exit 0，任一 FAIL exit 1。"""
    argparse.ArgumentParser(
        description="audit-kit × memsys 双包对拍（v4.3 合并不变量；无参数）").parse_args()
    work = tempfile.mkdtemp(prefix="crosscheck_")
    rc = 0
    try:
        for name, fn in (("双库同链", lambda: check_dual_chain(work)),
                         ("隔离面", lambda: check_isolation(_AUDKIT)),  # 审计对象=audit-kit 本体，不随脚本搬家
                         ("kind注册一致性", lambda: check_kinds(KINDS_YML))):
            try:
                ok, detail = fn()
            except Exception as e:                       # 检查器自身崩溃=FAIL，计入 detail 不吞
                ok, detail = False, f"检查器异常（fail-closed）：{type(e).__name__}: {e}"
            print(f"[{'PASS' if ok else 'FAIL'}] {name}：{detail}")
            if not ok:
                rc = 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
