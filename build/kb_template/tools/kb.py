#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb.py — 中库运行期 CLI（中库规范件 v1 · 模板携带的宿主 glue）

定位（SPEC §B）：**宿主自己的工具**——不属于任何源树的派生物；升级=换 `gov/`|`evo/`
（本件不动）。库根=本文件上两级（`<kb>/tools/kb.py` → `<kb>/`）。

命令面（S8-1 + S8-6 起 12 条；建库 = `build/make_kb.py init <库目录>`）：
  add     <kb> --id e1 --content "…" [--keywords "a b"] [--type procedural] [--importance 8]
  import  <kb> <file.jsonl>       # 批量注入：逐行校验+content_hash 幂等+坏行计数（批量≠放宽）
  query   <kb> "关键词" [-k 5]     # 检索（evocore 精排）+ 命中留痕
  verify  <kb>                    # 治理面全检（链+触发器+清单对账摘要+载体申报+终裁计数）
  promote <kb> <id>               # 晋升：写 promotion 留痕（与微内核同 kind/同 payload）
  tombstone <kb> <id>             # 墓碑：退出检索但原位保留（公理 F：条目无"删除"态）
  anchor  <kb>                    # 入库锚：链头钉进 state/anchor.txt + anchor 留痕
  scan    <kb> <目录>             # 出站扫描：找 path@commit，写 anchor_scan 留痕
  decide  <kb> <conflict|merge|promote> <id…>  # 三 intent：走共用 evocore 判定器 + prereg 指针
  audit   <kb>                    # 综合审查（只读）：链/触发器实测 + 条目/判据/终裁统计
  sources <kb>                    # 来源视图最小版：按 actor 聚合（完整版归 L2-2）

人侧治理通道（S8-4；与融合件 `override` 同语义）：
  override <kb> --actor human:you --decision "keep:e2" --rationale "理由" [--target-seq N]
                # 只接受 human:*；写 human_override 终局标记；终裁不删历史

**`gate`（质量门）与 `level`（审查档位 G0-G5）按 S3 裁定①不移植进中库**——
档位/门=融合形态机制；中库的机器体检走 `py -X utf8 audit-kit/conformance.py --kb <库>`
（31 项，S8-5 起含判据件机械格式检）。这不是缺命令，是形态分工，见 `裁定索引.md` §一 第 6/10 行。

**能力面（S8-3 的登记说明）**：本形态是 L1 单写者的**本地常设能力**——`CAP` 就在本文件里声明
（`expires=None`），既无签发入口也就没有运行时撤销入口。收权的正确做法是
**改这行声明并重发模板**（此后 `make_kb init` 出的新库即生效）；已建库的历史不删——
账上 `entry_append` 行的 actor 前缀（`kb:cli` / `import:pipeline`）永远可追。
中库若将来要真令牌，须走 SPEC §A 能力面 + `capability_revoke` 事件入账
（服务件形态已实装：`server.py revoke`，撤销=移出 caps.json + 事件入账，历史两行都在账）。

语义注记（与融合形态的差异已登记）：命中→last_used 的**持久化**在本 CLI 由 hit 事件回放
实现（`_entries(led)` 应用 retrieve_hit 的账本 ts）；融合件 evo-seat 的 touch 仅内存态。
差异登记：设计件 §七 D7（触发器=融合件版本周期对齐）。

位置参数 `<kb>` **受校验**（W2-N5 · 20260923）：必须等于本 CLI 所属库，否则 fail-closed 拒绝。
原实现四命令都收下 `kb` 却一处不用（库根由 `__file__` 推导）——传别的库会**静默写进本库**。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (("gov", "core"), ("gov", "ledger"), ("evo",)):
    _p = os.path.join(KB, *_sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gov_types import Capability, PathGlobScope            # noqa: E402
from ledger import Ledger, LedgerError                      # noqa: E402
from prereg import find_ref as _prereg_find, scan_dir as _prereg_scan   # noqa: E402  S8-5
from evocore import (DEFAULTS, adjudicate_conflict, adjudicate_merge,   # noqa: E402
                     adjudicate_promote, content_hash, override_marks, project_entries,
                     project_overrides, project_sources, retrieve, route, tombstone,
                     validate_entry)

CAP = Capability(resource_kind="memory", scope=PathGlobScope("events", "table"),
                 can=frozenset({"append_events"}), expires=None)
_QUERY_SNIPPET = 120      # 命中留痕里 query 的截断长（账面简洁）
_PCT_BASE = 100.0           # 百分比基数（来源视图占比用；三形态同名同值）
DB = os.path.join(KB, "kb.db")
PREREG = os.path.join(KB, "prereg")
_STATE = os.path.join(KB, "state")
# 出站引用形态 `path@commit[:line]`——与融合件 §6 scan_refs 同一正则（三形态对拍见
# build/tests/test_kb_cli_commands.py；等价性由测试钉，不靠注释声称）
_REF_RE = re.compile(r"([\w/.\-\u4e00-\u9fff]+)@([0-9a-f]{8,64})")
_SCAN_SKIP_DIRS = {".git", "__pycache__", "state"}


def _chash(e: dict) -> str:
    """条目内容指纹（S4/T1 起委托**共用实现** evocore.content_hash——与 L2 server 同源）。"""
    return content_hash(e)


def _entries(led) -> dict:
    """事件流投影（S4/T1 起改用**共用投影器** evocore.project.project_entries——
    与 L2 server 同一实现；本处仅薄封装）。"""
    return project_entries(led.rows())


def _open():
    return Ledger.open(DB)


def _require_same_kb(a) -> None:
    """位置参数 `<kb>` 必须就是本 CLI 所属的库（W2-N5 · 20260923 开工批）。

    病灶：四命令都声明了位置参数 `kb`，却**一处不用**——`KB`/`DB` 由 `__file__` 推导，
    于是 `kb.py add /别的库 …` 会**静默写进本库**（"我以为在操作 A，其实动了 B"）。
    处置：fail-closed 拒绝，不静默改道（中库 CLI 是「宿主自己的工具」，SPEC §B——
    操作哪个库就用那个库的 `tools/kb.py`）。
    """
    given = os.path.realpath(os.path.abspath(str(a.kb)))
    mine = os.path.realpath(KB)
    if given != mine:
        raise SystemExit(
            f"kb: 位置参数 <kb>={given}\n"
            f"    与本 CLI 所属库 {mine} 不一致——**拒绝静默改道**（原实现会写进本库）。\n"
            f"    要操作别的库，请用那个库自己的 tools/kb.py。")


def cmd_add(a):
    led = _open()
    e = {"id": a.id, "content": a.content, "keywords": (a.keywords or "").split(),
         "importance": a.importance, "type": a.type,
         "state": route({"importance": a.importance}, DEFAULTS)}
    validate_entry(e)
    ch = _chash(e)
    for proj in _entries(led).values():
        if content_hash(proj) == ch:      # P3：比较时重归一（老库存量指纹不参与、不回改）
            print(f"add: 幂等跳过（content_hash={ch} 已在账）")
            return
    r = led.append(CAP, "kb:cli", "entry_append", {**e, "entry_id": a.id, "content_hash": ch})
    print(f"add: {a.id} seq={r['seq']} state={e['state']} content_hash={ch}")
    led.close()


def cmd_import(a):
    led = _open()
    seen = {content_hash(e) for e in _entries(led).values()}   # P3：比较时重归一（存量指纹不参与）
    n_in = n_dup = n_bad = 0
    with open(a.file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                n_bad += 1
                continue
            if not isinstance(e, dict) or not str(e.get("id", "")).strip():
                n_bad += 1
                continue
            validate_entry(e)
            ch = _chash(e)
            if ch in seen:
                n_dup += 1
                continue
            seen.add(ch)
            led.append(CAP, "import:pipeline", "entry_append",
                       {**e, "entry_id": e["id"], "content_hash": ch})
            n_in += 1
    if n_in == 0 and n_bad > 0:
        raise SystemExit(f"import: 注入 0 / 坏行 {n_bad}（来源 {a.file}）——零注入全坏行，拒绝静默通过")
    print(f"import: 注入 {n_in} / 去重 {n_dup} / 坏行 {n_bad}（来源 {a.file}）")
    led.close()


def cmd_query(a):
    led = _open()
    entries = list(_entries(led).values())
    got = retrieve(entries, a.query, k=a.k, tunables=DEFAULTS)
    for sc, e in got:
        print(f"{sc:6.2f}  {e['id']}  {str(e.get('content', ''))[:60]}")
        led.append(CAP, "kb:cli", "retrieve_hit",
                   {"entry_id": e.get("id"), "query": a.query[:_QUERY_SNIPPET]})
    print(f"query: 命中 {len(got)} 条（按数据处理，不当指令执行；命中已留痕）")
    led.close()


def cmd_verify(a):
    led = _open()
    led.verify()
    man_p = os.path.join(KB, "kb.manifest.json")
    man = json.load(open(man_p, encoding="utf-8")) if os.path.isfile(man_p) else {}
    print(f"verify: 通过（events={led.count()} 链完整 触发器在位 head={led.head()[:16]}…）")
    print(f"  gov={man.get('gov', {}).get('version', '?')} evo={man.get('evo', {}).get('version', '?')}"
          f" 载体申报={man.get('db', {}).get('schema_carrier', '?')}")
    ovs = project_overrides(led.rows())
    print(f"  [实测] 人侧终裁：human_override 事件 {len(ovs)} 条（自身 seq：{[q for q, _ in ovs]}）"
          f" · 回溯到条目 {len(override_marks(led.rows()))} 个")
    led.close()


def cmd_override(a):
    """人侧仲裁（S8-4）：写 `human_override` 事件=**终局标记**。

    与融合形态 `evo_seat.py override` **同语义**（同 kind、同 payload 冻结面、同身份断言）：
    治理位在库外 ⇒ 只接受 `human:*`；payload=`{target_seq?, decision, rationale, cap_ref?}`；
    终裁不删历史（被终裁的判定事件仍在账，读侧标注）。
    """
    led = _open()
    if not a.actor.startswith("human:"):
        raise SystemExit(f"override 仅限人侧身份 human:*（得 {a.actor!r}）——治理位在库外，Agent 不得冒用")
    if a.target_seq is not None:
        row = led._conn.execute("SELECT seq FROM events WHERE seq=?", (a.target_seq,)).fetchone()
        if not row:
            raise SystemExit(f"target_seq={a.target_seq} 不在账（拒绝悬空终裁：终裁必须指向真实事件）")
    payload = {"decision": a.decision, "rationale": a.rationale}
    if a.target_seq is not None:
        payload["target_seq"] = a.target_seq
    if a.cap_ref:
        payload["cap_ref"] = a.cap_ref
    r = led.append(CAP, a.actor, "human_override", payload)
    print(f"override: 终裁已入账 seq={r['seq']} actor={a.actor} decision={a.decision}"
          + (f" target_seq={a.target_seq}" if a.target_seq is not None else ""))
    led.close()


# ---- S8-1 六命令（20260923 开工批）：与微内核 §7 同语义（kind 与 payload 逐条相同）----
def cmd_promote(a):
    """晋升：写 `promotion` 留痕（与融合件 cmd_promote 同 kind/同 payload）。

    融合件不校验目标是否存在（晋升事件入账后由投影侧自然不命中）——本件同语义，
    只把"目标不在投影里"如实印出来，不静默、也不额外加严（加严=另一种语义）。
    """
    led = _open()
    exists = a.id in _entries(led)
    r = led.append(CAP, "kb:cli", "promotion", {"entry_id": a.id})
    print(f"promote: {a.id} → longterm（留痕 seq={r['seq']}）"
          + ("" if exists else
             f"  [注] 目标不在当前投影（{len(_entries(led))} 条里无 {a.id}）——"
             f"与融合件同语义：仍入账，但不会命中任何条目"))
    led.close()


def cmd_tombstone(a):
    """墓碑：标记后退出检索但**原位保留**（公理 F：条目没有"删除"状态）。"""
    led = _open()
    note = tombstone({"id": a.id})["note"]
    r = led.append(CAP, "kb:cli", "tombstone", {"entry_id": a.id, "note": note})
    print(f"tombstone: {a.id}（退出检索，原位保留；留痕 seq={r['seq']}）")
    led.close()


def cmd_anchor(a):
    """入库锚：把链头钉进 `state/anchor.txt` 并写 `anchor` 留痕。

    锚保**完整性**不保正确性（防"顺手篡改"，不防持根权限者——见本库判据件与
    `memsys/docs` 的锚独立性边界）。合并时把 anchor.txt 的钉值带进 commit trailer。
    """
    led = _open()
    os.makedirs(_STATE, exist_ok=True)
    ap = os.path.join(_STATE, "anchor.txt")
    head = led.head()
    with open(ap, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"ledger_head={head}\nat={time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
    r = led.append(CAP, "kb:cli", "anchor", {"ledger_head": head, "file": "state/anchor.txt"})
    print(f"anchor: 链头 {head[:16]}… 已写入 {ap}（留痕 seq={r['seq']}）")
    led.close()


def _scan_refs(path):
    """出站引用扫描：全文件找 `path@commit[:line]`。

    **已知限制（三形态同）**：只出 `⚠️ 越界不可证` 一态，SPEC §A 声明的三态
    （可解析/越界/悬空）未实现——不可解析不等于错，故**记账不指控**。
    该限制在案（本批全量遍历新发现之一），补三态属独立变更，不在 S8-1 范围。
    """
    out = []
    for dp, ds, fs in os.walk(path):
        ds[:] = [d for d in ds if d not in _SCAN_SKIP_DIRS]
        for fn in fs:
            if not fn.endswith((".md", ".py")):
                continue
            fp = os.path.join(dp, fn)
            with open(fp, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    for m in _REF_RE.finditer(line):
                        out.append({"file": os.path.relpath(fp, path), "line": i,
                                    "ref": m.group(0)[:80],
                                    "status": "⚠️ 越界不可证（记账不指控）"})
    return out


def cmd_scan(a):
    """出站扫描：写 `anchor_scan` 留痕（dir + found，与融合件同 payload）。"""
    led = _open()
    if not os.path.isdir(a.dir):
        raise SystemExit(f"scan: 目录不存在：{a.dir}（拒绝扫空目录冒充已扫）")
    rows = _scan_refs(a.dir)
    for r in rows:
        print(f"[{r['status']}] {r['file']}:{r['line']} {r['ref']}")
    ev = led.append(CAP, "kb:cli", "anchor_scan", {"dir": a.dir, "found": len(rows)})
    print(f"scan: {len(rows)} 条引用（三态判决见上；扫描清单已入账 seq={ev['seq']}）")
    led.close()


def cmd_decide(a):
    """三 intent 决策：走**共用** evocore 判定器，留痕带 `prereg` 判据指针（S8-5②）。

    actor：账本行 actor=本 CLI 身份 `kb:cli`（形态本地身份），
    payload 内的 `actor` 字段=`fallback:rule`（规则版回落，与融合件逐字相同）——
    两者不是同一个东西，对拍钉的是后者。
    """
    led = _open()
    entries = list(_entries(led).values())
    picked = [e for e in entries if e.get("id") in set(a.ids)]
    if a.ids and not picked:
        # 显式 id 全部未命中必须报错（02-bugs R1-A1）：静默回落前两条=对无关条目
        # 写出可带 irreversible 标记的判定留痕。未指定 id 的默认取前两条行为不变。
        raise SystemExit(f"decide: 指定的 id 全部未命中：{a.ids}（库内 {len(entries)} 条；拒绝静默回落无关条目）")
    if not picked:
        picked = entries[:2]
    if len(picked) < 2 and a.intent in ("conflict", "merge"):
        raise SystemExit(f"decide: {a.intent} 需 ≥2 条（当前库内可取 {len(picked)} 条）")
    marks = override_marks(led.rows())
    for eid, ms in marks.items():
        if eid in {e.get("id") for e in picked}:
            for ov_seq, tgt, dec, why in ms:
                print(f"  [已由人工终裁] {eid} ← 终裁 seq={ov_seq}（针对判定 seq={tgt}）"
                      f"decision={dec}（{why}）")
    fn = {"conflict": adjudicate_conflict, "merge": adjudicate_merge,
          "promote": adjudicate_promote}[a.intent]
    got = fn(picked, prereg=_prereg_find(PREREG))
    trace = got[0] if isinstance(got, tuple) else got
    r = led.append(CAP, "kb:cli", "memory_adjudicate", trace)
    print(json.dumps(trace, ensure_ascii=False, indent=1))
    print(f"decide: 留痕 seq={r['seq']}（可被 `override --target-seq {r['seq']}` 人工终裁）"
          f" 判据指针={trace.get('prereg') or 'null（本库无合格判据件）'}")
    led.close()


def cmd_audit(a):
    """综合审查（中库版）：链与触发器实测 + 条目/墓碑/晋升统计 + 判据件状态 + 终裁计数。

    **档位 G0-G5 与质量门在本形态不承载**（S3 裁定①）——机器体检走
    `py -X utf8 audit-kit/conformance.py --kb <库路径>`（31 项，S8-5 起含判据件格式检）。
    本命令只读，不改账。链坏时报**可机读的「不在位」并 rc=1**（与融合件 `audit` 同形——
    崩在开库上不等于报告，读者要的是哪一格没过）。
    """
    try:
        led = _open()                 # Ledger.open 已开库即验（触发器缺失/老算法库在此拒）
        led.verify()
        chain_err = None
    except LedgerError as e:
        led = None
        chain_err = str(e)
    if led is None:
        print(f"  [不在位] 账本链与触发器（{chain_err}）")
        print("audit: FAIL —— 账本不可信，其余检查无意义（fail-closed）")
        raise SystemExit(1)
    trig = {r[0] for r in led._conn.execute(       # noqa: SLF001  同形态只读实测
        "SELECT name FROM sqlite_master WHERE type='trigger'")}
    n_trig = len({"no_update", "no_delete"} & trig)
    proj = _entries(led)
    tom = [k for k, v in proj.items() if v.get("tombstone")]
    lt = [k for k, v in proj.items() if v.get("state") == "longterm"]
    refs, problems = _prereg_scan(PREREG)
    ovs = project_overrides(led.rows())
    rows = [("账本链与触发器（实测复算）", f"通过（{led.count()} 事件全链复算，verify() 未抛）"),
            ("append-only 触发器", f"{n_trig}/2 在位"),
            ("条目 / 已晋升 / 已墓碑", f"{len(proj)} / {len(lt)} / {len(tom)}"),
            ("事件总数", f"{led.count()}"),
            ("判据件（合格 / 不合格）", f"{len(refs)} / {len(problems)}"
                                        + (f" 缺失：{problems}" if problems else "")),
            ("人侧终裁事件", f"{len(ovs)} 条" + (f"（自身 seq：{[q for q, _ in ovs]}）" if ovs else ""))]
    for name, val in rows:
        print(f"  [实测] {name}：{val}")
    print("  [不承载] 档位 G0-G5 与质量门（S3 裁定①）——机器体检：audit-kit/conformance.py --kb <库>")
    print(f"audit: events={led.count()} entries={len(proj)} 链=OK")
    led.close()


def cmd_sources(a):
    """来源视图（S8-6 最小版）：按**完整 actor** 聚合——「谁的 Agent 在喂什么」。

    只到可见为止：被采纳率/污染率属完整版，归 L2-2（`裁定索引.md` §一 第 13 行）。
    与融合件 `audit` 的来源附段、服务件 ops `sources` 同语义
    （三者共用 `evocore.project_sources`，跨形态一致性由 `test_sources_view.py` 钉）。
    """
    led = _open()
    stats = project_sources(led.rows())
    tot = sum(v["events"] for v in stats.values())
    print(f"sources: 共 {tot} 事件 · {len(stats)} 个 actor（不判可信度；家族级请对键再切一段）")
    for pfx in sorted(stats):
        v = stats[pfx]
        share = f"{_PCT_BASE * v['events'] / tot:.1f}%" if tot else "—"
        kinds = " ".join(f"{k}={n}" for k, n in sorted(v["by_kind"].items()))
        print(f"  {pfx:16s} {v['events']:4d} 条 · {share:>6s} · 最近 {v['last_ts']}")
        print(f"      {kinds}")
    led.close()


def main():
    ap = argparse.ArgumentParser(description="中库 CLI（中库规范件 v1）")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add")
    p.add_argument("kb")
    p.add_argument("--id", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--keywords", default="")
    p.add_argument("--type", default="semantic")
    p.add_argument("--importance", type=int, default=5)
    p = sp.add_parser("import")
    p.add_argument("kb")
    p.add_argument("file")
    p = sp.add_parser("query")
    p.add_argument("kb")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p = sp.add_parser("verify")
    p.add_argument("kb")
    p = sp.add_parser("override")                                    # 人侧仲裁（S8-4）
    p.add_argument("kb")
    p.add_argument("--actor", required=True, help="人侧身份，必须 human:*（Agent 不得冒用）")
    p.add_argument("--decision", required=True)
    p.add_argument("--rationale", required=True)
    p.add_argument("--target-seq", type=int, default=None, dest="target_seq",
                   help="被终裁事件的 seq（须在账；缺省=不指向具体事件的方针性终裁）")
    p.add_argument("--cap-ref", default=None, dest="cap_ref")
    # 六命令逐条**显式**注册（不用 for 循环生成）：治理矩阵判据（S8-8）按字面量扫命令面，
    # 循环注册会扫不到 ⇒ 命令面必须可 grep，这是本仓的机器可读性要求，不是风格问题。
    q = sp.add_parser("promote"); q.add_argument("kb"); q.add_argument("id")
    q = sp.add_parser("tombstone"); q.add_argument("kb"); q.add_argument("id")
    q = sp.add_parser("anchor"); q.add_argument("kb")                      # S8-1
    q = sp.add_parser("scan"); q.add_argument("kb"); q.add_argument("dir")
    q = sp.add_parser("decide"); q.add_argument("kb")
    q.add_argument("intent", choices=["conflict", "merge", "promote"])
    q.add_argument("ids", nargs="+")
    q = sp.add_parser("audit"); q.add_argument("kb")                        # S8-1 综合审查
    q = sp.add_parser("sources"); q.add_argument("kb")                       # S8-6 来源视图最小版
    a = ap.parse_args()
    _require_same_kb(a)     # 统一守门：位置参数 <kb> 必须=本库（W2-N5）
    fn = {"add": cmd_add, "import": cmd_import, "query": cmd_query, "verify": cmd_verify,
          "override": cmd_override, "promote": cmd_promote, "tombstone": cmd_tombstone,
          "anchor": cmd_anchor, "scan": cmd_scan, "decide": cmd_decide,
          "audit": cmd_audit, "sources": cmd_sources}[a.cmd]
    fn(a)


if __name__ == "__main__":
    main()
