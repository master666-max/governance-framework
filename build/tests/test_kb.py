# -*- coding: utf-8 -*-
"""test_kb.py — 中库规范件不变量测试（S3 · T5/T7/T10；《S3设计》§五 判据 1/2/5/6）

守的契约（负向必配正向对照）：
  ① 模板起真库跑通：init → add/import/query/verify 四命令全走 → conformance --kb PASS；
  ② **迁移三同 + 字节中立**（主判据）：融合件建的库迁移后 events 数/链头/全链摘要三项全同，
     且迁移动作对 db 字节中立（sha 前后相同）；迁移后 conformance --kb PASS；
  ③ 判别力四式（负向必抓）：改库内事件 · 改 gov 副本 · 改清单 · 抽触发器——四式**必 FAIL**；
  ④ 空转防护：被篡改的产物与干净态**确实相异**（否则"抓到"可能是假象）；
  ⑤ 跨工具公式同步：conformance `_aggregate` ≡ make_kb `_digest`（两份实现必须逐位同源）。
运行：py -X utf8 build/tests/test_kb.py
"""
import hashlib
import importlib.util
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
MK = os.path.join(ROOT, "build", "make_kb.py")
CONF = os.path.join(ROOT, "audit-kit", "conformance.py")
SEAT = os.path.join(ROOT, "evo-seat", "evo_seat.py")
_TMP = []


def _run(args):
    r = subprocess.run([sys.executable, "-X", "utf8", *args],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def _tmp(name):
    d = tempfile.mkdtemp(prefix=f"s3kb_{name}_")
    _TMP.append(d)
    return d


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _exec_tool(path, name):
    """工具以 exec 载入独立命名空间（本仓惯例；conformance 已守卫化不触发 main）。"""
    src = open(path, encoding="utf-8").read()
    ns = {"__file__": path, "__name__": name}
    exec(compile(src, path, "exec"), ns)   # sec-exempt: 载入对象=本仓 tracked 工具文件（非外部输入）
    return ns


class TestKb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = os.path.join(_tmp("demo"), "kb")
        rc, log = _run([MK, "init", cls.kb])
        assert rc == 0, log
        for args in (["add", cls.kb, "--id", "e1", "--content", "玻璃材质 IOR 1.45",
                      "--keywords", "玻璃 材质", "--type", "procedural", "--importance", "8"],
                     ["add", cls.kb, "--id", "e2", "--content", "三点布光 主光 45 度",
                      "--keywords", "布光", "--type", "procedural", "--importance", "7"]):
            rc2, log2 = _run([os.path.join(cls.kb, "tools", "kb.py"), *args])
            assert rc2 == 0, log2
        cls.lib = os.path.join(_tmp("lib"), "host.db")
        for args in (["init", cls.lib, "--level", "G1"],
                     ["append", cls.lib, "--id", "e1", "--content", "材质 玻璃 IOR",
                      "--keywords", "玻璃", "--type", "procedural", "--importance", "8"],
                     ["append", cls.lib, "--id", "e2", "--content", "布光 主光",
                      "--keywords", "布光", "--type", "procedural", "--importance", "7"]):
            rc3, log3 = _run([SEAT, *args])
            assert rc3 == 0, log3
        cls.kb2 = os.path.join(_tmp("mig"), "kb")
        rc4, log4 = _run([MK, "migrate", cls.lib, cls.kb2])
        assert rc4 == 0, log4
        cls.mig_log = log4

    @classmethod
    def tearDownClass(cls):
        for d in _TMP:
            shutil.rmtree(d, ignore_errors=True)

    def test_init_and_cli_roundtrip(self):
        """① 模板起真库跑通：四命令（已在上方实跑）+ conformance --kb PASS。"""
        rc, log = _run([CONF, "--kb", self.kb])
        self.assertEqual(rc, 0, log)
        self.assertIn("PASS", log)
        rc_q, log_q = _run([os.path.join(self.kb, "tools", "kb.py"), "query", self.kb, "玻璃", "-k", "3"])
        self.assertEqual(rc_q, 0, log_q)
        self.assertIn("e1", log_q)
        rc_v, log_v = _run([os.path.join(self.kb, "tools", "kb.py"), "verify", self.kb])
        self.assertEqual(rc_v, 0, log_v)

    def test_migrate_three_same_and_byte_neutral(self):
        """② 迁移三同 + 字节中立（主判据；读数取自迁移报告原文）。"""
        self.assertIn("三同判据", self.mig_log)
        self.assertIn("⇒ PASS", self.mig_log, self.mig_log)
        self.assertIn("迁移字节中立", self.mig_log)
        digest_now = _exec_tool(MK, "mk_probe")
        before = digest_now["chain_digest"](self.lib)
        after = digest_now["chain_digest"](os.path.join(self.kb2, "kb.db"))
        for k in ("events", "head", "digest"):
            self.assertEqual(before[k], after[k], f"三同判据 {k} 不一致")
        self.assertEqual(_sha(self.lib), _sha(os.path.join(self.kb2, "kb.db")), "迁移非字节中立")

    def test_migrated_kb_passes_conformance(self):
        """②续：迁移后体检 PASS（载体双认：融合库=meta 载体）。"""
        rc, log = _run([CONF, "--kb", self.kb2])
        self.assertEqual(rc, 0, log)

    def _tamper_db(self):
        """把 kb 复制一份，篡改其 kb.db（绕过触发器改事件）——返回新 kb 路径。"""
        t = os.path.join(_tmp("tamper"), "kb")
        shutil.copytree(self.kb, t)
        db = os.path.join(t, "kb.db")
        conn = sqlite3.connect(db)
        conn.executescript("DROP TRIGGER no_update; DROP TRIGGER no_delete;")
        conn.execute("UPDATE events SET self_hash=? WHERE seq=1", ("f" * 64,))
        conn.execute("DROP TRIGGER IF EXISTS no_delete")
        conn.commit()
        conn.close()
        return t

    def test_tamper_events_detected(self):
        """③a 改库内事件（含抽触发器）→ conformance --kb 必 FAIL。"""
        t = self._tamper_db()
        rc, log = _run([CONF, "--kb", t])
        self.assertNotEqual(rc, 0, "篡改未被检出")
        self.assertIn("FAIL", log)

    def test_tamper_gov_copy_detected(self):
        """③b 改 gov 副本一字节 → 必 FAIL（载荷对账）。"""
        t = os.path.join(_tmp("tamper2"), "kb")
        shutil.copytree(self.kb, t)
        with open(os.path.join(t, "gov", "core", "hashes.py"), "ab") as f:
            f.write(b"# tamper\n")
        rc, log = _run([CONF, "--kb", t])
        self.assertNotEqual(rc, 0, "gov 副本被改未被检出")
        self.assertIn("FAIL", log)

    def test_tamper_manifest_detected(self):
        """③c 改清单（aggregate 抹位）→ 必 FAIL。"""
        t = os.path.join(_tmp("tamper3"), "kb")
        shutil.copytree(self.kb, t)
        p = os.path.join(t, "kb.manifest.json")
        man = json.load(open(p, encoding="utf-8"))
        man["gov"]["aggregate_sha"] = "0" * 64
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(man, f, ensure_ascii=False, sort_keys=True, indent=2)
        rc, log = _run([CONF, "--kb", t])
        self.assertNotEqual(rc, 0, "清单被改未被检出")
        self.assertIn("FAIL", log)

    def test_negative_controls_differ(self):
        """④ 空转防护：篡改副本与干净态**确实相异**（防"抓到"是假象）。"""
        t = self._tamper_db()
        self.assertNotEqual(_sha(os.path.join(t, "kb.db")), _sha(os.path.join(self.kb, "kb.db")))
        rc_clean, _ = _run([CONF, "--kb", self.kb])
        self.assertEqual(rc_clean, 0, "干净态应 PASS（正向对照）")

    def test_aggregate_formula_synced(self):
        """⑤ 跨工具公式同步：conformance `_aggregate` ≡ make_kb `_digest`（逐位同源）。"""
        conf_ns = _exec_tool(CONF, "conf_probe")
        mk_ns = _exec_tool(MK, "mk_probe2")
        sample = {"a.py": "1" * 64, "b/c.py": "2" * 64}
        self.assertEqual(conf_ns["_aggregate"](sample), mk_ns["_digest"](sample))

    def test_kb_positional_mismatch_refused(self):
        """⑥ W2-N5（20260923 开工批）：位置参数 `<kb>` 指向**别的库** → fail-closed 拒绝。

        病灶（改前行为）：四命令都声明 `kb` 位置参数却一处不用，库根由 `__file__` 推导，
        于是 `kb.py verify /别的库` 会**静默体检本库并 rc=0**；`add /别的库 …` 会静默写进本库。
        本用例含正向对照（本库仍通过）与写命令守门（越库 add 被拒且本库事件数不变）。
        """
        cli = os.path.join(self.kb, "tools", "kb.py")
        rc, log = _run([cli, "verify", self.kb2])            # 指着另一个库（迁移出来的 kb2）
        self.assertNotEqual(rc, 0, "指向别的库未被拒——静默改道仍在")
        self.assertIn("拒绝静默改道", log)
        rc_ok, log_ok = _run([cli, "verify", self.kb])       # 正向对照：本库照常通过
        self.assertEqual(rc_ok, 0, log_ok)
        self.assertIn("verify: 通过", log_ok)
        n_before = int(re.search(r"events=(\d+)", log_ok).group(1))
        rc_w, log_w = _run([cli, "add", self.kb2, "--id", "zz", "--content", "越库写入探针"])
        self.assertNotEqual(rc_w, 0, log_w)                  # 写命令同样守门
        _rc_n, log_n = _run([cli, "verify", self.kb])
        n_after = int(re.search(r"events=(\d+)", log_n).group(1))
        self.assertEqual(n_before, n_after, "越库 add 仍写进了本库（事件数变了）")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCmdImport(unittest.TestCase):
    """P1 欠账清偿（20260924）：批量入口 cmd_import 的四路 + 负向（预注册-三件推进 波P1）。"""

    @classmethod
    def setUpClass(cls):
        cls.kb = os.path.join(_tmp("imp"), "kb")
        rc, log = _run([MK, "init", cls.kb])
        assert rc == 0, log
        cls.kbpy = os.path.join(cls.kb, "tools", "kb.py")

    def _imp(self, content):
        f = os.path.join(_tmp("imp"), "in.jsonl")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(content)
        return _run([self.kbpy, "import", self.kb, f])

    def test_good_lines(self):
        rc, log = self._imp('{"id":"i1","content":"玻璃 IOR","keywords":"玻璃","type":"procedural","importance":8}\n'
                            '{"id":"i2","content":"布光 三点","keywords":"布光","type":"procedural","importance":7}\n')
        self.assertEqual(rc, 0)
        self.assertIn("注入 2", log)
        self.assertIn("坏行 0", log)

    def test_bad_lines_counted(self):
        rc, log = self._imp('not-json\n{"no_id":true}\n'
                            '{"id":"i3","content":"合法条目","keywords":"x","type":"semantic","importance":3}\n')
        self.assertEqual(rc, 0)
        self.assertIn("注入 1", log)
        self.assertIn("坏行 2", log)

    def test_all_bad_rejected(self):
        """负向：零注入全坏行必须 rc≠0（fail-closed）——没导入东西不得判通过。"""
        rc, log = self._imp('not-json\n{"no_id":true}\n')
        self.assertNotEqual(rc, 0)
        self.assertIn("拒绝静默通过", log)

    def test_dedup_by_content(self):
        line = '{"id":"d1","content":"重复内容去重验证","keywords":"x","type":"semantic","importance":3}\n'
        rc1, _ = self._imp(line)
        self.assertEqual(rc1, 0)
        rc2, log2 = self._imp(line)
        self.assertEqual(rc2, 0)
        self.assertIn("注入 0", log2)
        self.assertIn("去重 1", log2)

    def test_verify_still_ok(self):
        rc, log = _run([self.kbpy, "verify", self.kb])
        self.assertEqual(rc, 0)
