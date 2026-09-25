# -*- coding: utf-8 -*-
"""test_ops_governance.py — S8-2（服务件 audit/gate）+ S8-3（撤销）+ S8-6（来源视图）验收

对应《S8工单》三条的验收条款：
  S8-2「两命令实跑读数；`--help` 列出；八工具清单**不变**（回归）」
  S8-3「撤销→该 grant 写操作被拒（`DENY:NO_CAP`）+ `capability_revoke` 在账；撤销前后链完整」
  S8-6「三形态各自输出 actor 聚合读数；**与账本直查数字一致**（独立复算对拍）」

负向对照三处：①门找不到 ⇒ 必须 rc=1（绝不"没跑成却报通过"）；②坏库进 audit ⇒ rc=1；
③撤不存在的 grant ⇒ rc=1。另有一处**跨形态同输入对拍**（融合件 `_source_stats`
vs 重装形态 `project_sources`），防两抄本各走各的。

用法: py -X utf8 build/tests/test_ops_governance.py
"""
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRV_OUT = os.path.join(ROOT, "build", "out", "server")
KB_CLI_SRC = os.path.join(ROOT, "build", "kb_template", "tools", "kb.py")
MK = os.path.join(ROOT, "build", "make_kb.py")
CONF = os.path.join(ROOT, "audit-kit", "conformance.py")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)                       # evocore 可导入（跨形态对拍要）
PY = [sys.executable, "-X", "utf8"]
_TMP = []
_LOG_SNIP = 400                    # 断言失败时回显输出的截断长


def _run(args):
    r = subprocess.run([*PY, *args], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def _tmp(name):
    d = tempfile.mkdtemp(prefix=f"s8ops_{name}_")
    _TMP.append(d)
    return d


def _deploy():
    if not os.path.isdir(SRV_OUT):
        raise AssertionError(f"装配产物缺失：{SRV_OUT}——先跑 `py -X utf8 build/assemble.py all`")
    d = os.path.join(_tmp("srv"), "server")
    shutil.copytree(SRV_OUT, d, ignore=shutil.ignore_patterns("__pycache__", "calls.jsonl", "caps.json"))
    return os.path.join(d, "server.py"), d


def _call_stdio(server, libs_root, calls, grant=None):
    """grant=该批调用使用的接入键（B′·L2_GRANT 环境变量）；None=不携带（用于无键 DENY 测试）。"""
    reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26",
                        "clientInfo": {"name": "t", "version": "1"}, "capabilities": {}}}]
    reqs += [{"jsonrpc": "2.0", "id": i + 2, "method": "tools/call", "params": p}
             for i, p in enumerate(calls)]
    inp = "".join(json.dumps(r) + "\n" for r in reqs)
    env = {**os.environ, "L2_GRANT": grant} if grant else None
    r = subprocess.run([*PY, server, "--libs-root", libs_root], input=inp,
                       capture_output=True, text=True, encoding="utf-8", env=env)
    return r.stdout, r.stderr


def _append_args(lib, eid):
    return {"name": "memory_append",
            "arguments": {"lib": lib, "id": eid, "content": f"样本 {eid}", "importance": 5}}


class _FakeStore:
    """给 `_source_stats` 喂与 `project_sources` 相同的行（跨形态同输入对拍）。"""

    def __init__(self, rows):
        self._rows = rows

    def rows(self):
        return iter(self._rows)


class TestOpsGate(unittest.TestCase):
    """S8-2：`gate` 只是仓级门的入口——结果与退出码**原样透传**。"""

    @classmethod
    def setUpClass(cls):
        cls.server, cls.dir = _deploy()

    def test_gate_exit_passthrough_both_ways(self):
        gate_py = os.path.join(ROOT, "tools", "code_quality_gate.py")
        # 负向夹具=**显式第三方 import**。原先这里靠"不给 --allow"制造失败，
        # 而本仓模块面入白名单（W5 批 FIRST_PARTY）之后那个前提就没了——
        # 靠仪器缺陷立起来的负向对照，会被修好仪器的那一刻静默废掉。
        probe = os.path.join(_tmp("probe"), "probe_third_party.py")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("import requests\n\nx = 1\n")
        args = [self.server, "gate", probe, "--gate", gate_py]
        rc_bad, log_bad = _run(args)
        self.assertNotEqual(rc_bad, 0, "第三方依赖该拒却放行：透传失效")
        self.assertIn("不在白名单", log_bad)
        rc_ok, log_ok = _run([self.server, "gate", KB_CLI_SRC, "--gate", gate_py])
        self.assertEqual(rc_ok, 0, log_ok)                  # 本仓件 ⇒ 不必手传 --allow 也应过
        self.assertIn("代码质量门：通过", log_ok)
        self.assertNotEqual(rc_bad, rc_ok, "两种结果同一个码 ⇒ 透传是假的")
        self.assertIn(gate_py, log_ok, "须回显实际调用的门路径（可复核）")

    def test_missing_gate_refuses_not_passes(self):
        """负向对照：门找不到 ⇒ rc=1。找不到仪器绝不能等于"仪器通过"。"""
        rc, log = _run([self.server, "gate", KB_CLI_SRC, "--gate",
                        os.path.join(_tmp("no"), "根本没有这个门.py")])
        self.assertNotEqual(rc, 0, "门缺失却 rc=0")
        self.assertIn("REFUSE", log)
        self.assertIn("--gate", log, "拒因必须给出可操作的补救路径")

    def test_help_lists_new_ops(self):
        rc, log = _run([self.server, "--help"])
        self.assertEqual(rc, 0, log)
        for name in ("audit", "gate", "revoke", "sources", "override"):
            self.assertIn(name, log, f"ops {name} 未出现在 --help")


class TestOpsAudit(unittest.TestCase):
    """S8-2：逐库巡检；任一库链坏 ⇒ 整体 rc=1（不许"报了就算过"）。"""

    @classmethod
    def setUpClass(cls):
        cls.server, cls.dir = _deploy()
        cls.libs = os.path.join(_tmp("libs"), "libs")
        for lib, g, pfx in (("a.db", "g1", "llm:alpha"), ("b.db", "g2", "llm:beta")):
            rc, log = _run([cls.server, "init", "--libs-root", cls.libs, "--lib", lib,
                            "--grant-id", g, "--actor-prefix", pfx])
            assert rc == 0, log
        _call_stdio(cls.server, cls.libs, [_append_args("a.db", "x1")], grant="g1")
        _call_stdio(cls.server, cls.libs, [_append_args("b.db", "y1")], grant="g2")

    def test_audit_healthy_root_passes(self):
        rc, log = _run([self.server, "audit", "--libs-root", self.libs])
        self.assertEqual(rc, 0, log)
        self.assertIn("链坏=0", log)
        for name in ("a.db", "b.db"):
            self.assertIn(name, log)
        self.assertIn("来源汇总", log)

    def test_audit_broken_lib_is_graded_and_fails(self):
        """负向对照：摘掉一个库的触发器 ⇒ 报「[不在位]」+ rc=1（不抛栈、不静默跳过）。"""
        bad = os.path.join(_tmp("bak"), "libs")
        shutil.copytree(self.libs, bad)
        for name in ("a.db", "b.db"):
            os.chmod(os.path.join(bad, name), stat.S_IRUSR | stat.S_IWUSR)
        conn = sqlite3.connect(os.path.join(bad, "a.db"))
        conn.executescript("DROP TRIGGER no_update; DROP TRIGGER no_delete;")
        conn.close()
        rc, log = _run([self.server, "audit", "--libs-root", bad])
        self.assertNotEqual(rc, 0, "有坏库却 rc=0")
        self.assertIn("[不在位] a.db", log, log[-_LOG_SNIP:])
        self.assertIn("链坏=1", log)
        self.assertNotIn("Traceback", log, "巡检崩了不等于巡检通过")

    def test_eight_tools_unchanged(self):
        """S8-2 回归条款：ops 扩面不得动协议面八工具。"""
        src = open(os.path.join(SRV_OUT, "server.py"), encoding="utf-8").read()
        import re
        m = re.search(r"^TOOL_FUNCS = \{(.+?)\}$", src, re.S | re.M)
        names = set(re.findall(r'"([a-z_]+)":', m.group(1)))
        self.assertEqual(names, {"memory_append", "memory_retrieve", "memory_promote",
                                 "memory_tombstone", "memory_verify", "anchor", "scan",
                                 "adjudicate"})


class TestRevoke(unittest.TestCase):
    """S8-3：撤销=入账 + 移出 caps.json；只收被撤的那个 grant。

    **每个用例一套独立部署位与 libs**（setUp 而非 setUpClass）：
    `caps.json` 的权威位＝**`libs_root` 旁**（P2 作用域修复后的正确位；W3e 时代曾挂在
    安装位——那是已登记的缺陷）。共用一份部署位时，前一个用例撤走的令牌会让
    后一个用例的断言串味，故每用例独立 libs 的理由不变。
    这个作用域本身是**已登记的既有设计缺陷**（见 02-自检读数 §W3e：
    两个 `--libs-root` 共用一个安装位即共享/互清令牌表，归 L2-2 caps 签发链）。
    """

    def setUp(self):
        self.server, self.dir = _deploy()
        self.libs = os.path.join(_tmp("rv"), "libs")
        for lib, g, pfx in (("a.db", "g1", "llm:alpha"), ("b.db", "g2", "llm:beta")):
            rc, log = _run([self.server, "init", "--libs-root", self.libs, "--lib", lib,
                            "--grant-id", g, "--actor-prefix", pfx])
            assert rc == 0, log

    def _kinds(self, lib):
        c = sqlite3.connect(os.path.join(self.libs, lib))
        out = [(s, a, k, json.loads(p)) for s, a, k, p in
               c.execute("SELECT seq,actor,kind,payload FROM events ORDER BY seq")]
        c.close()
        return out

    def _write_ok(self, out):
        """一次写入成功的判据：回了条目 id 与 content_hash，且没有 DENY/REFUSE 前缀。"""
        self.assertIn('"id"', out)
        self.assertIn("content_hash", out)
        self.assertNotIn("DENY:", out)
        self.assertNotIn("REFUSE:", out)

    def test_revoke_removes_only_that_grant(self):
        out, _ = _call_stdio(self.server, self.libs, [_append_args("a.db", "pre1")], grant="g1")
        self._write_ok(out)
        rc, log = _run([self.server, "revoke", "--libs-root", self.libs,
                        "--grant-id", "g1", "--reason", "测试台收权"])
        self.assertEqual(rc, 0, log)
        self.assertIn("capability_revoke", log)
        self.assertIn("历史不删", log)
        rows = self._kinds("a.db")
        kinds = [k for _s, _a, k, _p in rows]
        self.assertEqual(kinds.count("capability_revoke"), 1)
        self.assertEqual(kinds.count("capability_issue"), 2, "两次签发都必须在账")
        rev = [p for _s, _a, k, p in rows if k == "capability_revoke"][0]
        self.assertEqual(rev["grant_id"], "g1")
        self.assertEqual(rev["reason"], "测试台收权")
        self.assertIn("was", rev, "撤销事件须带被收回的原始签发内容（读账可复原）")
        out2, _ = _call_stdio(self.server, self.libs, [_append_args("a.db", "post1")], grant="g2")
        self._write_ok(out2)
        self.assertIn("post1", out2)
        acts = {a for _s, a, k, _p in self._kinds("a.db") if k == "entry_append"}
        self.assertEqual(acts, {"llm:alpha:g1", "llm:beta:g2"},
                         f"两身份应各自留痕，实得 {acts}")
        with open(os.path.join(self.libs, "caps.json"), encoding="utf-8") as f:
            caps = json.load(f)
        self.assertEqual([c["grant_id"] for c in caps["caps"]], ["g2"])

    def test_full_deny_when_no_cap_left(self):
        """撤销**全部** grant ⇒ 写必须 `DENY:NO_CAP`（撤销不生效比撤销生效更危险）。"""
        rc, log = _run([self.server, "revoke", "--libs-root", self.libs, "--grant-id", "g1"])
        self.assertEqual(rc, 0, log)
        rc2, log2 = _run([self.server, "revoke", "--libs-root", self.libs, "--grant-id", "g2"])
        self.assertEqual(rc2, 0, log2)
        out, _ = _call_stdio(self.server, self.libs, [_append_args("a.db", "after")])
        self.assertIn("NO_CAP", out, f"撤空令牌后仍能写：{out[:_LOG_SNIP]}")
        c = sqlite3.connect(os.path.join(self.libs, "a.db"))
        ids = [json.loads(p).get("id") for p in
               c.execute("SELECT payload FROM events WHERE kind='entry_append'")]
        c.close()
        self.assertEqual(ids, [], "被拒的写入竟然入了账")

    def test_revoke_unknown_grant_refused(self):
        rc, log = _run([self.server, "revoke", "--libs-root", self.libs, "--grant-id", "nope"])
        self.assertNotEqual(rc, 0, "撤不存在的 grant 却成功")
        self.assertIn("NO_GRANT", log)

    def test_chain_intact_around_revoke(self):
        """撤销前后链必须完整（S8-3 验收原话）——用 conformance 复验，不自己宣布。"""
        _run([self.server, "revoke", "--libs-root", self.libs, "--grant-id", "g2"])
        kb = os.path.join(_tmp("chain"), "kb")
        self.assertEqual(_run([MK, "init", kb])[0], 0)
        shutil.copyfile(os.path.join(self.libs, "a.db"), os.path.join(kb, "kb.db"))
        rc, log = _run([CONF, "--kb", kb])
        self.assertIn("链重放", log)
        self.assertNotIn("哈希不符", log, f"撤销链动了账本完整性：{log[-_LOG_SNIP:]}")

    def test_kind_registered(self):
        with open(os.path.join(ROOT, "build", "l2server", "kinds.yml"), encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("capability_revoke:", txt)
        blk = txt.split("capability_revoke:", 1)[1]
        self.assertIn('actor_pattern: "human:*"', blk)
        self.assertIn("authority_level: 4", blk)


class TestSourcesAcrossForms(unittest.TestCase):
    """S8-6：三形态同输入同读数，且与账本直查一致（独立复算）。"""

    ROWS = [(1, "2026-09-24T00:00:01", "llm:alpha:g1", "entry_append", "{}", "p" * 64, "h" * 64),
            (2, "2026-09-24T00:00:02", "llm:beta:g2", "entry_append", "{}", "p" * 64, "h" * 64),
            (3, "2026-09-24T00:00:03", "llm:alpha:g1", "retrieve_hit", "{}", "p" * 64, "h" * 64),
            (4, "2026-09-24T00:00:09", "human:root", "capability_issue", "{}", "p" * 64, "h" * 64)]

    def test_two_forms_agree_on_same_rows(self):
        from evocore import project_sources
        spec = __import__("importlib.util", fromlist=["util"])
        seat = os.path.join(ROOT, "evo-seat", "evo_seat.py")
        st = spec.spec_from_file_location("_seat_src", seat)
        mod = spec.module_from_spec(st)
        st.loader.exec_module(mod)
        a = project_sources(self.ROWS)
        b = mod._source_stats(_FakeStore(self.ROWS))
        self.assertEqual(a, b, f"跨形态来源聚合漂移：{a} vs {b}")
        self.assertEqual(a["llm:alpha:g1"]["events"], 2)
        self.assertEqual(a["llm:alpha:g1"]["last_ts"], "2026-09-24T00:00:03")

    def test_prefix_would_have_merged_two_agents(self):
        """登记在案的设计偏离复现：按首段前缀聚合会把两个 Agent 并成一桶。"""
        from evocore import project_sources
        st = project_sources(self.ROWS)
        fam = {}
        for k, v in st.items():
            fam.setdefault(k.split(":")[0], 0)
            fam[k.split(":")[0]] += v["events"]
        self.assertEqual(len(st), 3, "完整 actor 应有 3 个来源")
        self.assertEqual(len(fam), 2, "截前缀只剩 2 桶——正是要避免的信息损失")
        self.assertEqual(fam["llm"], 3)

    def test_cli_sources_matches_direct_sql(self):
        kb = os.path.join(_tmp("src"), "kb")
        self.assertEqual(_run([MK, "init", kb])[0], 0)
        cli = os.path.join(kb, "tools", "kb.py")
        for eid in ("s1", "s2"):
            self.assertEqual(_run([cli, "add", kb, "--id", eid, "--content", f"内容 {eid}",
                                   "--keywords", "词", "--importance", "5"])[0], 0)
        _rc, log = _run([cli, "query", kb, "内容", "-k", "3"])
        rc, out = _run([cli, "sources", kb])
        self.assertEqual(rc, 0, out)
        c = sqlite3.connect(os.path.join(kb, "kb.db"))
        direct = {a: n for a, n in c.execute("SELECT actor, COUNT(*) FROM events GROUP BY actor")}
        c.close()
        self.assertIn(f"sources: 共 {sum(direct.values())} 事件", out, out)
        for actor, n in direct.items():
            self.assertIn(f"{actor:16s} {n:4d} 条", out,
                          f"{actor} 直查 {n} 条，与 CLI 读数不符：{out}")

    def test_empty_lib_no_crash(self):
        kb = os.path.join(_tmp("es"), "kb")
        self.assertEqual(_run([MK, "init", kb])[0], 0)
        rc, out = _run([os.path.join(kb, "tools", "kb.py"), "sources", kb])
        self.assertEqual(rc, 0, out)
        self.assertIn("共 0 事件", out, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
