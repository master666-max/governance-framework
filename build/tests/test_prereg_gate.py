# -*- coding: utf-8 -*-
"""test_prereg_gate.py — S8-5 判据生效机制的机械判据（20260923 开工批）

承载《S8工单》S8-5 的验收条款：
  「留痕含 prereg 指针（两形态对拍一致）；判据件缺版本行时体检报 **FAIL**（负向对照）；
    升级后行为对拍差异 0（字段为新增）」

三件事各有一段：
  ① 判据件**机械格式**（`audit-kit/core/prereg.py` + `conformance --kb/--host`）；
  ② 决策**留痕带判据指针**（`evocore/decision.py` 的 `prereg` 字段；服务件端到端）；
  ③ **加法式不伤旧账**（老留痕无该键 → 读侧按 null 容错）与**行为对拍仍零差异**。

用法: py -X utf8 build/tests/test_prereg_gate.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)                       # evocore 可导入（②的留痕用例要）
sys.path.insert(0, os.path.join(ROOT, "audit-kit", "core"))
import prereg as P                                            # noqa: E402  被测件（治理核 L0）
CONF = os.path.join(ROOT, "audit-kit", "conformance.py")
MK = os.path.join(ROOT, "build", "make_kb.py")
SRV_OUT = os.path.join(ROOT, "build", "out", "server")
KB_STARTER = os.path.join(ROOT, "build", "kb_template", "prereg", "判据-起步-v1.md")
_TMP = []
OUT_SNIPPET = 400        # 断言失败时回显的输出的截断长（仅影响可读性，非机制参数）


def _run(args):
    r = subprocess.run([sys.executable, "-X", "utf8", *args], capture_output=True, text=True,
                       encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def _tmp(name):
    d = tempfile.mkdtemp(prefix=f"s8pr_{name}_")
    _TMP.append(d)
    return d


def _write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


GOOD = "# 判据 X\n\n> 生效：2026-09-23。版本：v3。判据锚：x-main-v3\n\n正文。\n"
NO_VER = "# 判据 Y\n\n> 生效：2026-09-23。\n\n正文。\n"
NO_DATE = "# 判据 Z\n\n> 版本：v1。\n\n正文。\n"
EN_VER = "# 判据 W\n\nversion: v2\neffective: 2026-09-24\n\n正文。\n"


class TestPreregFormat(unittest.TestCase):
    """① 机械格式：必检两项 + 派生锚 + 自带锚优先。"""

    def setUp(self):
        self.d = _tmp("fmt")

    def test_good_file_parses(self):
        info = P.parse(GOOD)
        self.assertEqual(info["version"], "v3")
        self.assertEqual(info["effective"], "2026-09-23")
        self.assertEqual(info["anchor"], "x-main-v3")
        self.assertEqual(P.missing_markers(GOOD), [])

    def test_english_markers_accepted(self):
        self.assertEqual(P.missing_markers(EN_VER), [])
        self.assertEqual(P.parse(EN_VER)["version"], "v2")

    def test_missing_version_detected(self):
        self.assertEqual(P.missing_markers(NO_VER), ["版本行"])

    def test_missing_effective_detected(self):
        self.assertEqual(P.missing_markers(NO_DATE), ["生效日行"])

    def test_scan_dir_skips_readme_and_sorts(self):
        _write(self.d, "README.md", "目录说明，无版本无日期\n")
        _write(self.d, "b-判据.md", NO_VER)
        _write(self.d, "a-判据.md", GOOD)
        refs, problems = P.scan_dir(self.d)
        self.assertEqual([n for n, _ in refs], ["a-判据.md"], f"README 应被跳过：{refs}")
        self.assertEqual([n for n, _ in problems], ["b-判据.md"])
        self.assertEqual(refs[0][1], "x-main-v3", "自带判据锚应优先于派生锚")

    def test_anchor_falls_back_to_derived(self):
        _write(self.d, "c-件.md", "# 无自带锚\n版本：v1\n生效：2026-09-23\n")
        refs, problems = P.scan_dir(self.d)
        self.assertEqual(problems, [])
        self.assertEqual(refs[0][1], "c-件.md@v1", "无自带锚时应派生 <名>@<版本>")

    def test_find_ref_none_when_empty(self):
        self.assertIsNone(P.find_ref(self.d), "空目录必须给 None（留痕写 null）")
        self.assertIsNone(P.find_ref(os.path.join(self.d, "不存在")))
        _write(self.d, "README.md", "只有说明件\n")
        self.assertIsNone(P.find_ref(self.d), "只有 README（非判据件）也算无判据可依")

    def test_unreadable_file_reported_not_swallowed(self):
        p = os.path.join(self.d, "bad.md")
        with open(p, "wb") as f:
            f.write(b"\xff\xfe\x00 not utf-8 \x00")
        refs, problems = P.scan_dir(self.d)
        self.assertEqual(refs, [])
        self.assertEqual(len(problems), 1, f"不可读件必须进 problems 而不是静默跳过：{problems}")


class TestDecisionTraceCarriesPointer(unittest.TestCase):
    """② 留痕带判据指针（加法式）；③ 老留痕容错。"""

    ENTRIES = [{"id": "e1", "importance": 5, "source": "manual", "created_at": "2026-09-20T00:00:00"},
               {"id": "e2", "importance": 8, "created_at": "2026-09-21T00:00:00"}]

    def test_all_three_intents_carry_prereg(self):
        from evocore import adjudicate_conflict, adjudicate_merge, adjudicate_promote
        for name, fn in (("conflict", adjudicate_conflict), ("merge", adjudicate_merge),
                         ("promote", adjudicate_promote)):
            got = fn(self.ENTRIES, prereg="kb-starter-v1")
            trace = got[0] if isinstance(got, tuple) else got
            self.assertIn("prereg", trace, f"{name} 留痕缺 prereg 字段")
            self.assertEqual(trace["prereg"], "kb-starter-v1", name)

    def test_default_is_null_not_missing(self):
        from evocore import adjudicate_merge
        trace = adjudicate_merge(self.ENTRIES)
        self.assertIn("prereg", trace, "默认也要有该键（值 null），否则新旧留痕结构不同形")
        self.assertIsNone(trace["prereg"])

    def test_old_trace_without_key_tolerated(self):
        """③ 老库兼容：换代前写入的留痕**没有** prereg 键——读侧取 None 不得炸。"""
        old_trace = {"kind": "memory_adjudicate", "intent": "merge", "entries": ["e1", "e2"],
                     "decision": "defer", "rationale": "r", "ts": "2026-09-22T00:00:00",
                     "actor": "fallback:rule", "severity_if_wrong": "redundant"}
        self.assertNotIn("prereg", old_trace)
        self.assertIsNone(old_trace.get("prereg"))
        rows = [(1, "2026-09-22T00:00:00", "fallback:rule", "memory_adjudicate",
                 json.dumps(old_trace), "p" * 64, "h" * 64)]
        from evocore import project_entries
        self.assertEqual(project_entries(rows), {}, "判定事件本就不建条（前向兼容）")


class TestConformanceGate(unittest.TestCase):
    """①的体检落地：--kb / --host 升级检，且**缺项即 FAIL**（负向对照）。"""

    def _mk_kb(self, name):
        kb = os.path.join(_tmp(name), "kb")
        rc, log = _run([MK, "init", kb])
        self.assertEqual(rc, 0, log)
        return kb

    def test_template_kb_passes_with_prereg_item(self):
        kb = self._mk_kb("ok")
        self.assertTrue(os.path.isfile(os.path.join(kb, "prereg", "判据-起步-v1.md")),
                        "模板必须自带起步判据件（否则新建库出厂即缺判据）")
        rc, log = _run([CONF, "--kb", kb])
        self.assertEqual(rc, 0, log)
        self.assertIn("判据件可引用", log)

    def test_missing_version_line_fails(self):
        """负向对照（验收原话）：判据件缺版本行 ⇒ 体检 FAIL。"""
        kb = self._mk_kb("nover")
        p = os.path.join(kb, "prereg", "判据-起步-v1.md")
        with open(p, encoding="utf-8") as f:
            text = f.read()
        _write(os.path.join(kb, "prereg"), "判据-起步-v1.md", text.replace("版本：v1。", ""))
        rc, log = _run([CONF, "--kb", kb])
        self.assertNotEqual(rc, 0, "缺版本行竟然仍 PASS ⇒ 检查是空的")
        self.assertIn("FAIL", log)
        self.assertIn("版本行", log)

    def test_removing_all_criteria_fails(self):
        """负向对照二：判据件全删（只剩 README）⇒ FAIL，不再被"目录非空"蒙过。"""
        kb = self._mk_kb("empty")
        os.remove(os.path.join(kb, "prereg", "判据-起步-v1.md"))
        rc, log = _run([CONF, "--kb", kb])
        self.assertNotEqual(rc, 0, "只剩 README 竟然仍 PASS ⇒「有判据」与「空目录」仍同形")
        self.assertIn("判据件可引用", log)

    def test_host_side_item_present_and_passing(self):
        rc, log = _run([CONF, "--kernel", os.path.join(ROOT, "audit-kit"),
                        "--host", "memsys"])
        self.assertEqual(rc, 0, log)
        self.assertIn("§B 宿主 判据件可引用", log)
        self.assertNotIn("FAIL", log)              # 不写恒真断言：只断「无 FAIL」+ 该项在位
        self.assertRegex(log, r"conformance: \d+/\d+ PASS")

    def test_vendored_checker_ships_with_kb(self):
        """中库体检用**库自带**的 gov 副本（副本缺件即验不出）。"""
        kb = self._mk_kb("gov")
        self.assertTrue(os.path.isfile(os.path.join(kb, "gov", "core", "prereg.py")))

    def test_old_kb_copy_reports_clean_failure_not_crash(self):
        """老库（gov 副本早于 S8-5，没有检查器）⇒ 必须是**可机读的 FAIL**，
        不是抛 FileNotFoundError——崩在检查器加载上属仪器坏，不是被测物坏。"""
        kb = self._mk_kb("old")
        os.remove(os.path.join(kb, "gov", "core", "prereg.py"))
        rc, log = _run([CONF, "--kb", kb])
        self.assertNotEqual(rc, 0, "副本过旧却整体 PASS ⇒ 静默放过")
        self.assertIn("判据检查器在位", log, log[-OUT_SNIPPET:])
        self.assertIn("升级=换 gov/ 目录", log, "FAIL 必须给升级路径")
        self.assertNotIn("FileNotFoundError", log, "抛栈了：仪器崩而不是报 FAIL")
        self.assertNotIn("Traceback", log, "抛栈了：仪器崩而不是报 FAIL")


class TestServerEndToEnd(unittest.TestCase):
    """②的服务件端到端：adjudicate 留痕真的带上锚。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(SRV_OUT):
            raise AssertionError(f"装配产物缺失：{SRV_OUT}——先跑 `py -X utf8 build/assemble.py all`")
        cls.d = _tmp("srv")
        cls.srvdir = os.path.join(cls.d, "server")
        shutil.copytree(SRV_OUT, cls.srvdir,
                        ignore=shutil.ignore_patterns("__pycache__", "calls.jsonl", "caps.json"))
        cls.server = os.path.join(cls.srvdir, "server.py")
        cls.libs = os.path.join(cls.d, "libs")
        rc, log = _run([cls.server, "init", "--libs-root", cls.libs, "--lib", "a.db",
                        "--grant-id", "g1", "--actor-prefix", "llm:t"])
        assert rc == 0, log
        cls.kb_anchor_file = os.path.join(cls.srvdir, "prereg", "判据-起步-v1.md")

    def test_prereg_slot_ships_with_server(self):
        self.assertTrue(os.path.isfile(self.kb_anchor_file),
                        "装配未下发 prereg 骨架（assemble.L2SERVER_FILES 缺项？）")

    def test_adjudicate_trace_carries_anchor(self):
        """走 stdio 调一次 adjudicate，断留痕 prereg=件内自带锚 `l2-starter-v1`。"""
        reqs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26",
                        "clientInfo": {"name": "t", "version": "1"}, "capabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "memory_append",
                "arguments": {"lib": "a.db", "id": "e1", "content": "偏好 A", "importance": 5,
                              "source": "manual"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "memory_append",
                "arguments": {"lib": "a.db", "id": "e2", "content": "偏好 B", "importance": 8}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "adjudicate",
                "arguments": {"lib": "a.db", "intent": "conflict", "ids": ["e1", "e2"]}}},
        ]
        inp = "".join(json.dumps(r) + "\n" for r in reqs)
        r = subprocess.run([sys.executable, "-X", "utf8", self.server,
                            "--libs-root", self.libs],
                           input=inp, capture_output=True, text=True, encoding="utf-8",
                           cwd=self.srvdir, env={**os.environ, "L2_GRANT": "g1"})
        got = {}
        for line in r.stdout.splitlines():
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("id") == 4:
                got = m
        self.assertTrue(got, f"没拿到 id=4 的响应：{r.stdout[:OUT_SNIPPET]}{r.stderr[:OUT_SNIPPET]}")
        txt = json.dumps(got, ensure_ascii=False)
        self.assertIn("l2-starter-v1", txt,
                      f"adjudicate 留痕未带判据锚：{txt[:OUT_SNIPPET]}")
        self.assertNotIn('"prereg": null', txt, "判据件在位却写了 null")

    def test_null_when_prereg_removed(self):
        """负向对照：删掉本部署的判据件 ⇒ 留痕 prereg=null（读账即知当时无判据可依）。"""
        bak = self.kb_anchor_file + ".bak"
        shutil.move(self.kb_anchor_file, bak)
        try:
            reqs = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-03-26",
                            "clientInfo": {"name": "t", "version": "1"}, "capabilities": {}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "adjudicate",
                    "arguments": {"lib": "a.db", "intent": "merge", "ids": ["e1", "e2"]}}},
            ]
            inp = "".join(json.dumps(x) + "\n" for x in reqs)
            r = subprocess.run([sys.executable, "-X", "utf8", self.server,
                                "--libs-root", self.libs],
                               input=inp, capture_output=True, text=True, encoding="utf-8",
                               cwd=self.srvdir, env={**os.environ, "L2_GRANT": "g1"})
            trace = None
            for line in r.stdout.splitlines():
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if m.get("id") == 2:
                    inner = json.loads(m["result"]["content"][0]["text"])
                    trace = inner.get("trace")
            self.assertIsNotNone(trace, f"没解析到 adjudicate 留痕：{r.stdout[:OUT_SNIPPET]}")
            self.assertIn("prereg", trace, "留痕必须带 prereg 键（值可为 null，键不可缺）")
            self.assertIsNone(trace["prereg"],
                              f"判据件已删，指针应为 null，实得 {trace['prereg']!r}")
        finally:
            shutil.move(bak, self.kb_anchor_file)


class TestStarterCriteriaCommitted(unittest.TestCase):
    """起步判据件本体：机械可检 + 不冒充领域判据。"""

    def test_kb_starter_has_markers_and_disclaims(self):
        with open(KB_STARTER, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(P.missing_markers(text), [], "模板起步判据件自身必须过格式检")
        self.assertEqual(P.parse(text)["anchor"], "kb-starter-v1")
        self.assertIn("尚未注入领域判据", text, "起步件必须如实声明「沿用默认」，不得冒充领域判据")


if __name__ == "__main__":
    unittest.main(verbosity=2)
