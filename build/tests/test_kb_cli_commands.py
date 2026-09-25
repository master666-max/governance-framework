# -*- coding: utf-8 -*-
"""test_kb_cli_commands.py — S8-1 中库六命令 + **三形态留痕对拍**（20260923 开工批）

承载《S8工单》S8-1 验收：「六命令实跑；**三形态留痕对拍**（同一操作序列在微内核与中库
产生的 kind/payload 语义逐条相同，**差异为空或挂登记**）」。

对拍的硬处在于"挂登记"三个字：本件不是断言"两边一样"，而是
  · 实测两边差在哪 ⇒ 与 `KNOWN_DIVERGENCE` 登记的字段集**必须完全相等**；
  · 冒出没登记的新差异 ⇒ FAIL（防"顺手改一边"）；
  · 登记过但差异已消失 ⇒ 也 FAIL（防过期登记变成永久豁免——同 `S1_verify_behavior` 的反空转闸）；
  · 比较器本身有负向对照（人为注入差异必须被抓）。

账本行 actor 列**不参与对拍**（那是形态本地身份：融合件 `engine` / 中库 `kb:cli`）；
留痕 payload 内的 `actor` 字段（`fallback:rule`）参与——两者不是一个东西。

用法: py -X utf8 build/tests/test_kb_cli_commands.py
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEAT = os.path.join(ROOT, "evo-seat", "evo_seat.py")
KB_CLI = os.path.join(ROOT, "build", "kb_template", "tools", "kb.py")
MK = os.path.join(ROOT, "build", "make_kb.py")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from evocore import tombstone as _evo_tombstone   # noqa: E402  共用实现（中库侧 note 的基准）

PY = [sys.executable, "-X", "utf8"]
_TMP = []

IN_SCOPE = ("promotion", "tombstone", "anchor", "anchor_scan", "memory_adjudicate")
# 形态本地词汇（W2-N3 已登记：投影器两认，故不作为差异计）
APPEND_VOCAB = {"fused": "memory_append", "kb": "entry_append"}
# 已登记的跨形态差异（字段级；"ts" 是时钟，全局归一化，不逐条登记）
KNOWN_DIVERGENCE = {
    "memory_adjudicate": {"rationale", "actor", "prereg"},
    # 融合件 §5 是规则版的简化抄本（rationale 文案更短、actor=engine）；
    # prereg 键只在重装形态有——融合件的 _trace 在 framework_sha 覆盖的机制段，
    # 改它须走版本闸流程。登记处：02-自检读数 §W3b-五 + 裁定索引 §二。
    "tombstone": {"note"},
    # 本批对拍新抓出的真漂移（不是假设）：融合件 §4 note=「退出检索，原位保留」，
    # evocore 版=「退出检索，原位保留（审计窗口）」——语义同、文案差四字。
    # 补齐要动 §4（framework_sha 覆盖段）⇒ 与本表 prereg 同源，走版本闸流程再改。
    # 语义核心（"退出检索，原位保留"）由 test_parity_on_the_equal_fields 断言两侧都在。
    "anchor": {"ledger_head"},        # 两库内容不同，链头必然不同
}
NORMALIZED_KEYS = {"ts"}               # 时钟字段：两侧格式同、值必然不同
_LOG_SNIP = 400                    # 失败时回显子进程输出的截断长（仅影响可读性）


def _run(args):
    r = subprocess.run([*PY, *args], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def _tmp(name):
    d = tempfile.mkdtemp(prefix=f"s8kb_{name}_")
    _TMP.append(d)
    return d


def _rows(db, kinds=None):
    q = "SELECT seq, actor, kind, payload FROM events"
    if kinds:
        q += " WHERE " + " OR ".join(f"kind='{k}'" for k in kinds)
    c = sqlite3.connect(db)          # 只读用法（不写）；Windows 盘符路径不适合 URI 形式
    out = {}
    for _seq, _actor, kind, payload in c.execute(q + " ORDER BY seq"):
        out.setdefault(kind, []).append(json.loads(payload))
    c.close()
    return out


def _diff(kind, a, b):
    """两侧 payload 的字段级差异集（含只在一侧出现的键）。"""
    keys = (set(a) | set(b)) - NORMALIZED_KEYS
    out = set()
    for k in keys:
        if k not in a or k not in b or a.get(k) != b.get(k):
            out.add(k)
    return out


class TestThreeFormsLedgerParity(unittest.TestCase):
    """S8-1 主判据：同一操作序列 ⇒ kind 全等、payload 差异 == 已登记集。"""

    @classmethod
    def setUpClass(cls):
        cls.fx = _tmp("fx")
        with open(os.path.join(cls.fx, "refs.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# 夹具\n\n出处写法示例 docs/x.md@1bad2511:12\n另一条 src/a.py@deadbeef99:3\n")
            # 提交号须 ≥8 位十六进制——这是扫描器自身的规则（`1bad251` 七位不算）

        cls.fused_db = os.path.join(_tmp("f"), "lib.db")
        cls.kb = os.path.join(_tmp("k"), "kb")
        assert _run([SEAT, "init", cls.fused_db, "--level", "G5"])[0] == 0
        assert _run([MK, "init", cls.kb])[0] == 0
        cls.kb_cli = os.path.join(cls.kb, "tools", "kb.py")
        cls.kb_db = os.path.join(cls.kb, "kb.db")
        seq = (
            (["append", cls.fused_db, "--id", "e1", "--content", "玻璃 IOR 1.45",
              "--keywords", "玻璃 材质", "--importance", "5"],
             ["add", cls.kb, "--id", "e1", "--content", "玻璃 IOR 1.45",
              "--keywords", "玻璃 材质", "--importance", "5"]),
            (["append", cls.fused_db, "--id", "e2", "--content", "布光 主光 45 度",
              "--keywords", "布光", "--type", "procedural", "--importance", "8"],
             ["add", cls.kb, "--id", "e2", "--content", "布光 主光 45 度",
              "--keywords", "布光", "--type", "procedural", "--importance", "8"]),
            (["promote", cls.fused_db, "e1"], ["promote", cls.kb, "e1"]),
            (["tombstone", cls.fused_db, "e2"], ["tombstone", cls.kb, "e2"]),
            (["anchor", cls.fused_db], ["anchor", cls.kb]),
            (["scan", cls.fused_db, cls.fx], ["scan", cls.kb, cls.fx]),
            (["decide", cls.fused_db, "conflict", "e1", "e2"],
             ["decide", cls.kb, "conflict", "e1", "e2"]),
        )
        for fargs, kargs in seq:
            rc1, log1 = _run([SEAT, *fargs])
            rc2, log2 = _run([cls.kb_cli, *kargs])
            assert rc1 == 0, f"融合件 {fargs[0]} 失败：{log1}"
            assert rc2 == 0, f"中库 {kargs[0]} 失败：{log2}"

    @classmethod
    def tearDownClass(cls):
        for d in _TMP:
            shutil.rmtree(d, ignore_errors=True)

    def test_same_kinds_same_counts(self):
        a = _rows(self.fused_db, IN_SCOPE)
        b = _rows(self.kb_db, IN_SCOPE)
        self.assertEqual(set(a), set(b), f"kind 集合不同：{sorted(set(a) ^ set(b))}")
        self.assertEqual(set(a), set(IN_SCOPE), f"应有入范围的 {IN_SCOPE}，实得 {sorted(a)}")
        for k in IN_SCOPE:
            self.assertEqual(len(a[k]), len(b[k]), f"{k} 事件数不同")
            self.assertEqual(len(a[k]), 1, f"{k} 应恰好 1 条（跑了两遍？）")

    def test_append_vocab_is_form_local(self):
        """条目写入用形态本地 kind（W2-N3 两认）——不是差异，但必须**看得见**是哪一个。"""
        for form, db in (("fused", self.fused_db), ("kb", self.kb_db)):
            kinds = set(_rows(db))
            self.assertIn(APPEND_VOCAB[form], kinds,
                          f"{form} 应写 {APPEND_VOCAB[form]}，实得 {sorted(kinds)}")

    def test_payload_divergence_equals_registered(self):
        a = _rows(self.fused_db, IN_SCOPE)
        b = _rows(self.kb_db, IN_SCOPE)
        actual = {}
        for k in IN_SCOPE:
            d = _diff(k, a[k][0], b[k][0])
            if d:
                actual[k] = d
        self.assertEqual(actual, KNOWN_DIVERGENCE,
                         f"差异集与登记不符。实得={actual}\n登记={KNOWN_DIVERGENCE}\n"
                         f"（新增差异=某边被顺手改过；登记过期=请把 KNOWN_DIVERGENCE 同步删掉）")

    def test_parity_on_the_equal_fields(self):
        """非登记字段必须真等（防"全字段都登记成差异"把对拍掏空）。"""
        a = _rows(self.fused_db, IN_SCOPE)
        b = _rows(self.kb_db, IN_SCOPE)
        self.assertEqual(a["promotion"][0], b["promotion"][0], "promotion payload 应逐字相同")
        core = "退出检索，原位保留"
        for form, row in (("fused", a["tombstone"][0]), ("kb", b["tombstone"][0])):
            self.assertTrue(row["note"].startswith(core),
                            f"{form} 墓碑 note 丢了语义核心「{core}」：{row['note']}")
            self.assertEqual(row["entry_id"], "e2")
        self.assertEqual(b["tombstone"][0]["note"], _evo_tombstone({"id": "e2"})["note"],
                         "中库侧 note 必须与共用 evocore 逐字相同")
        self.assertEqual(a["anchor_scan"][0], b["anchor_scan"][0],
                         f"扫描留痕应相同（同一夹具）：{a['anchor_scan'][0]} vs {b['anchor_scan'][0]}")
        self.assertEqual(a["anchor_scan"][0]["found"], 2, "夹具本应有 2 条引用——0 说明扫描器空转")
        self.assertEqual(a["memory_adjudicate"][0]["decision"], b["memory_adjudicate"][0]["decision"])
        self.assertEqual(a["memory_adjudicate"][0]["actor"], "engine")
        self.assertEqual(b["memory_adjudicate"][0]["actor"], "fallback:rule",
                         "中库走共用 evocore 判定器；其规则版回落身份必须是 fallback:rule")

    def test_comparator_is_not_vacuous(self):
        """负向对照：人为造一个新差异，比较器必须报出来。"""
        self.assertEqual(_diff("promotion", {"entry_id": "e1"}, {"entry_id": "e1"}), set())
        self.assertEqual(_diff("promotion", {"entry_id": "e1"}, {"entry_id": "e9"}), {"entry_id"})
        self.assertEqual(_diff("promotion", {"entry_id": "e1"}, {"entry_id": "e1", "extra": 1}),
                         {"extra"}, "只在一侧出现的键也必须算差异（prereg 就是这么抓的）")


class TestSixCommandsBehaviors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = os.path.join(_tmp("beh"), "kb")
        rc, log = _run([MK, "init", cls.kb])
        assert rc == 0, log
        cls.cli = os.path.join(cls.kb, "tools", "kb.py")
        rc2, log2 = _run([cls.cli, "add", cls.kb, "--id", "e1", "--content", "玻璃 IOR 1.45",
                          "--keywords", "玻璃", "--importance", "5"])
        assert rc2 == 0, log2

    @classmethod
    def tearDownClass(cls):
        for d in _TMP:
            shutil.rmtree(d, ignore_errors=True)

    def test_scan_nonexistent_dir_refused(self):
        rc, log = _run([self.cli, "scan", self.kb, os.path.join(_tmp("no"), "根本不存在")])
        self.assertNotEqual(rc, 0, "扫不存在的目录竟然成功 ⇒ 与「扫了没东西」同形")
        self.assertIn("拒绝扫空目录", log)

    def test_decide_needs_two_entries(self):
        rc, log = _run([self.cli, "decide", self.kb, "conflict", "e1"])
        self.assertNotEqual(rc, 0, log)
        self.assertIn("≥2", log)

    def test_promote_unknown_id_matches_fused_semantics(self):
        """融合件对不存在的 id 也入账（不做存在性闸门）——中库同语义，但必须**说出来**。"""
        rc, log = _run([self.cli, "promote", self.kb, "ghost"])
        self.assertEqual(rc, 0, f"若在此加严，就与融合件不同语义了：{log}")
        self.assertIn("目标不在当前投影", log)

    def test_tombstone_removes_from_query(self):
        rc, log = _run([self.cli, "query", self.kb, "玻璃", "-k", "3"])
        self.assertEqual(rc, 0, log)
        self.assertIn("e1", log)
        _run([self.cli, "tombstone", self.kb, "e1"])
        rc2, log2 = _run([self.cli, "query", self.kb, "玻璃", "-k", "3"])
        self.assertEqual(rc2, 0, log2)
        self.assertNotIn("e1", log2, "墓碑后仍被召回 ⇒ 违反公理 F 的反面")
        rc3, log3 = _run([self.cli, "verify", self.kb])
        self.assertEqual(rc3, 0, "墓碑不许破坏链：" + log3)

    def test_audit_reports_and_is_readonly(self):
        before = _rows(os.path.join(self.kb, "kb.db"))
        rc, log = _run([self.cli, "audit", self.kb])
        self.assertEqual(rc, 0, log)
        self.assertIn("账本链与触发器（实测复算）", log)
        self.assertIn("[不承载]", log, "audit 必须自述档位/门不承载，免得读者以为查过")
        self.assertEqual(_rows(os.path.join(self.kb, "kb.db")), before, "audit 不许写账")

    def test_audit_broken_chain_is_graded_failure_not_crash(self):
        bad = os.path.join(_tmp("bad"), "kb")
        shutil.copytree(self.kb, bad)
        conn = sqlite3.connect(os.path.join(bad, "kb.db"))
        conn.executescript("DROP TRIGGER no_update; DROP TRIGGER no_delete;")
        conn.close()
        rc, log = _run([os.path.join(bad, "tools", "kb.py"), "audit", bad])
        self.assertNotEqual(rc, 0, "链被破坏后 audit 仍 rc=0")
        self.assertIn("不在位", log, f"应出分级报告而不是抛栈：{log[-_LOG_SNIP:]}")
        self.assertIn("FAIL", log)
        self.assertNotIn("Traceback", log, "崩在开库上不等于报告")


class TestFormDivisionDocumented(unittest.TestCase):
    """gate/level 不在中库 = 形态分工（S3 裁定①），不是漏装——必须在源里说得出。"""

    def _cmds(self, path):
        src = open(path, encoding="utf-8").read()
        return set(re.findall(r'add_parser\(\s*"([a-z][a-z0-9_]*)"', src))

    def test_gate_and_level_absent_in_kb_present_in_fused(self):
        kb, fused = self._cmds(KB_CLI), self._cmds(SEAT)
        for name in ("gate", "level"):
            self.assertIn(name, fused, f"融合件应有 {name}")
            self.assertNotIn(name, kb, f"中库不该有 {name}（S3 裁定①）")
        for name in ("promote", "tombstone", "anchor", "scan", "decide", "audit", "override"):
            self.assertIn(name, kb, f"S8-1/S8-4 应有 {name}，实得 {sorted(kb)}")

    def test_absence_is_documented_in_source(self):
        src = open(KB_CLI, encoding="utf-8").read()
        self.assertIn("S3 裁定①", src, "不承载的理由必须写在 CLI 头注里，不能只在测试里")
        self.assertIn("conformance.py --kb", src, "头注须给出中库体检的实际入口")
        self.assertNotIn("for name in (", src,
                        "命令面须逐条字面注册（矩阵按字面量扫；循环注册会成暗格）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
