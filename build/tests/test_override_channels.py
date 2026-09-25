# -*- coding: utf-8 -*-
"""test_override_channels.py — S8-4 人侧仲裁三通道的机械判据（20260923 开工批）

承载《S8工单-治理操作面补齐》S8-4 的验收条款：
  「三通道实跑：写 override → 事件在账（kind=human_override，actor=human:*）→ 该冲突条目状态查询显示终裁标记」
以及 S8 出口门 #3「三形态语义一致：同一操作序列产生的 kind/payload 语义逐条相同」。

三形态的通道位（治理位在库外 ⇒ 人侧动作**只在 CLI/ops**，不进协议八工具）：
  微内核（融合单文件）  `evo_seat.py override <库> --actor human:* …`
  中库（包内自足）      `<kb>/tools/kb.py override <kb> --actor human:* …`
  共库（L2 服务件）     `server.py override --libs-root … --lib … --actor human:* …`（**ops 面**）

用法: py -X utf8 build/tests/test_override_channels.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEAT = os.path.join(ROOT, "evo-seat", "evo_seat.py")
MK = os.path.join(ROOT, "build", "make_kb.py")
SERVER_SRC = os.path.join(ROOT, "build", "l2server", "server.py")   # 协议面回归读源件
SERVER_OUT = os.path.join(ROOT, "build", "out", "server")            # 可跑件=装配产物（源件不能单跑：缺 kernel/）
PY = [sys.executable, "-X", "utf8"]
_TMP = []


def _deploy_server():
    """把装配产物复制到临时位再跑——ops 会写 caps.json / ops/calls.jsonl，
    直接跑产物目录会留下运行期残件（HANDOVER 坑13：残件使 reconcile 报 DRIFT）。"""
    if not os.path.isdir(SERVER_OUT):
        raise AssertionError(f"装配产物缺失：{SERVER_OUT}——先跑 `py -X utf8 build/assemble.py all`")
    d = tempfile.mkdtemp(prefix="s8ov_srv_")
    _TMP.append(d)
    srv = os.path.join(d, "server")
    shutil.copytree(SERVER_OUT, srv,
                    ignore=shutil.ignore_patterns("__pycache__", "calls.jsonl", "caps.json"))
    return os.path.join(srv, "server.py")

# payload 冻结面（S8工单 S8-4）：{target_seq?, decision, rationale, cap_ref?}
FROZEN_KEYS = {"target_seq", "decision", "rationale", "cap_ref"}
REQUIRED_KEYS = {"decision", "rationale"}


def _run(args):
    r = subprocess.run([*PY, *args], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def _tmp(name):
    d = tempfile.mkdtemp(prefix=f"s8ov_{name}_")
    _TMP.append(d)
    return d


def _events(db, kind=None):
    import sqlite3
    c = sqlite3.connect(db)
    q = "SELECT seq, actor, kind, payload FROM events" + (f" WHERE kind='{kind}'" if kind else "")
    rows = [(s, a, k, json.loads(p)) for s, a, k, p in c.execute(q + " ORDER BY seq")]
    c.close()
    return rows


class TestOverrideChannels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 微内核库（G4：decide 需要）
        cls.seat_db = os.path.join(_tmp("seat"), "ov.db")
        rc, log = _run([SEAT, "init", cls.seat_db, "--level", "G4"])
        assert rc == 0, log
        for eid, imp in (("e1", "5"), ("e2", "8")):
            rc2, log2 = _run([SEAT, "append", cls.seat_db, "--id", eid,
                              "--content", f"玻璃 IOR {eid}", "--keywords", "玻璃", "--importance", imp])
            assert rc2 == 0, log2
        rc3, log3 = _run([SEAT, "decide", cls.seat_db, "conflict", "e1", "e2"])
        assert rc3 == 0, log3
        cls.seat_adj_seq = int(re.search(r"留痕 seq=(\d+)", log3).group(1))

        # 中库
        cls.kb = os.path.join(_tmp("kb"), "kb")
        rc4, log4 = _run([MK, "init", cls.kb])
        assert rc4 == 0, log4
        cls.kb_cli = os.path.join(cls.kb, "tools", "kb.py")
        for eid, imp in (("e1", "5"), ("e2", "8")):
            rck, logk = _run([cls.kb_cli, "add", cls.kb, "--id", eid,
                              "--content", f"玻璃 IOR {eid}", "--keywords", "玻璃",
                              "--importance", imp])
            assert rck == 0, logk

        # 服务件（部署到临时位 + 独立 libs-root，避免污染产物目录）
        cls.server = _deploy_server()
        cls.libs = _tmp("srvlibs")
        rc5, log5 = _run([cls.server, "init", "--libs-root", cls.libs, "--lib", "demo.db",
                          "--grant-id", "g1", "--actor-prefix", "llm:local"])
        assert rc5 == 0, log5
        cls.srv_db = os.path.join(cls.libs, "demo.db")

        # 三通道各写一次终裁（在 setUpClass 做，**不依赖用例执行顺序**——unittest 按字母序跑）
        cls.seat_ov_log = _run([SEAT, "override", cls.seat_db, "--actor", "human:boss",
                                "--decision", "keep:e2", "--rationale", "实测折射率优先",
                                "--target-seq", str(cls.seat_adj_seq)])
        cls.kb_ov_log = _run([cls.kb_cli, "override", cls.kb, "--actor", "human:boss",
                              "--decision", "keep:e2", "--rationale", "实测折射率优先",
                              "--target-seq", "1"])
        cls.srv_ov_log = _run([cls.server, "override", "--libs-root", cls.libs, "--lib", "demo.db",
                               "--actor", "human:boss", "--decision", "keep:e2",
                               "--rationale", "实测折射率优先", "--target-seq", "1"])
        for tag, (rc6, log6) in (("fused", cls.seat_ov_log), ("kb", cls.kb_ov_log),
                                 ("server", cls.srv_ov_log)):
            assert rc6 == 0, f"{tag} override 失败：{log6}"
        # 基线计数（负向用例据此断言"拒了就是拒了，没有报错但已写"）
        cls.base_counts = {"fused": len(_events(cls.seat_db, "human_override")),
                           "kb": len(_events(os.path.join(cls.kb, "kb.db"), "human_override")),
                           "server": len(_events(cls.srv_db, "human_override"))}

    @classmethod
    def tearDownClass(cls):
        for d in _TMP:
            shutil.rmtree(d, ignore_errors=True)

    # ---- 正向：三通道都把终裁写进账 ----
    def test_fused_channel_writes_event(self):
        rc, log = self.seat_ov_log
        self.assertEqual(rc, 0, log)
        self.assertIn("终裁已入账", log)
        ev = _events(self.seat_db, "human_override")
        self.assertEqual(len(ev), self.base_counts["fused"], log)
        self.assertEqual(ev[0][1], "human:boss")
        self.assertEqual(ev[0][3]["decision"], "keep:e2")
        self.assertEqual(ev[0][3]["target_seq"], self.seat_adj_seq,
                         "终裁须指向真实判定事件的 seq")

    def test_kb_channel_writes_event(self):
        rc, log = self.kb_ov_log
        self.assertEqual(rc, 0, log)
        self.assertIn("终裁已入账", log)
        ev = _events(os.path.join(self.kb, "kb.db"), "human_override")
        self.assertEqual(len(ev), self.base_counts["kb"], log)
        self.assertEqual(ev[0][1], "human:boss")

    def test_server_ops_channel_writes_event(self):
        rc, log = self.srv_ov_log
        self.assertEqual(rc, 0, log)
        self.assertIn("终裁已入账", log)
        ev = _events(self.srv_db, "human_override")
        self.assertEqual(len(ev), self.base_counts["server"], log)
        self.assertEqual(ev[0][1], "human:boss")

    # ---- 三形态语义一致（S8 出口门 #3）----
    def test_three_forms_same_kind_and_payload(self):
        """同一操作序列在三形态产生**同 kind、同 actor、同 payload 键集与值**。"""
        shapes = {}
        for name, db in (("fused", self.seat_db),
                         ("kb", os.path.join(self.kb, "kb.db")),
                         ("server", self.srv_db)):
            ev = _events(db, "human_override")
            self.assertEqual(len(ev), self.base_counts[name], f"{name} 终裁事件数与基线不符")
            _seq, actor, kind, payload = ev[0]
            # 对拍口径：`target_seq` 是**库内局部指针**（各库事件序号天然不同），不属跨形态语义面；
            # 语义面 = kind + actor 身份族 + payload 键集 + 终裁内容（decision/rationale）。
            shapes[name] = (actor, kind, tuple(sorted(payload)),
                            payload.get("decision"), payload.get("rationale"))
            self.assertIsInstance(payload.get("target_seq"), int,
                                  f"{name} 的 target_seq 应为 int（库内指针）")
            self.assertTrue(_events(db)[int(payload["target_seq"]) - 1],
                            f"{name} 的 target_seq 指向了不存在的事件")
        canon = {k: json.dumps(v, ensure_ascii=False) for k, v in shapes.items()}
        self.assertEqual(len(set(canon.values())), 1,
                         f"三形态留痕语义不一致：{canon}")
        actor, kind, keys, _dec, _why = shapes["fused"]
        self.assertEqual(kind, "human_override")
        self.assertTrue(actor.startswith("human:"), "actor 必须 human:*（治理位在库外）")
        self.assertTrue(REQUIRED_KEYS <= set(keys), f"缺必备键：{keys}")
        self.assertTrue(set(keys) <= FROZEN_KEYS,
                        f"payload 超出冻结面 {sorted(FROZEN_KEYS)}：{sorted(keys)}")

    # ---- 负向：三通道都必须拒 Agent 冒用与悬空终裁 ----
    def test_agent_identity_refused_in_all_three(self):
        cases = [
            [SEAT, "override", self.seat_db, "--actor", "llm:gpt:g1", "--decision", "d", "--rationale", "r"],
            [self.kb_cli, "override", self.kb, "--actor", "llm:gpt:g1", "--decision", "d", "--rationale", "r"],
            [self.server, "override", "--libs-root", self.libs, "--lib", "demo.db",
             "--actor", "llm:local:g1", "--decision", "d", "--rationale", "r"],
        ]
        for args in cases:
            rc, log = _run(args)
            self.assertNotEqual(rc, 0, f"Agent 冒用人侧身份未被拒：{args[0]}")
            self.assertNotIn("终裁已入账", log, f"竟然写进账了：{log}")
        # 账上没有多出终裁事件（拒了就是拒了，不能"报错但已写"）
        self.assertEqual(len(_events(self.seat_db, "human_override")), self.base_counts["fused"])
        self.assertEqual(len(_events(os.path.join(self.kb, "kb.db"), "human_override")),
                         self.base_counts["kb"])
        self.assertEqual(len(_events(self.srv_db, "human_override")), self.base_counts["server"])

    def test_dangling_target_seq_refused(self):
        for tag, args in (("fused",
                           [SEAT, "override", self.seat_db, "--actor", "human:b",
                            "--decision", "d", "--rationale", "r", "--target-seq", "99999"]),
                          ("kb",
                           [self.kb_cli, "override", self.kb, "--actor", "human:b",
                            "--decision", "d", "--rationale", "r", "--target-seq", "99999"]),
                          ("server",
                           [self.server, "override", "--libs-root", self.libs, "--lib", "demo.db",
                            "--actor", "human:b", "--decision", "d", "--rationale", "r",
                            "--target-seq", "99999"])):
            rc, log = _run(args)
            self.assertNotEqual(rc, 0, f"{tag} 悬空终裁未被拒")
            self.assertNotIn("终裁已入账", log, f"{tag} 悬空终裁竟然写进账了：{log}")
        self.assertEqual(len(_events(self.seat_db, "human_override")), self.base_counts["fused"],
                         "悬空终裁被拒后账上不应多出事件")

    # ---- 终裁标记可见（读侧）----
    def test_fused_decide_shows_override_marker(self):
        rc, log = _run([SEAT, "decide", self.seat_db, "conflict", "e1", "e2"])
        self.assertEqual(rc, 0, log)
        self.assertIn("已由人工终裁", log)
        self.assertIn(f"针对判定 seq={self.seat_adj_seq}", log)

    def test_fused_audit_reports_override_count(self):
        rc, log = _run([SEAT, "audit", self.seat_db])
        self.assertEqual(rc, 0, log)
        self.assertRegex(log, r"human_override 事件 \d+ 条")

    def test_kb_verify_reports_override_count(self):
        rc, log = _run([self.kb_cli, "verify", self.kb])
        self.assertEqual(rc, 0, log)
        self.assertRegex(log, r"human_override 事件 \d+ 条")

    # ---- kind 注册（宿主三件事之一）----
    def test_kind_registered_in_host_registries(self):
        for rel in (os.path.join("build", "kb_template", "kinds.yml"),
                    os.path.join("build", "l2server", "kinds.yml"),
                    os.path.join("memsys", "kinds.yml")):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                txt = fh.read()
            self.assertIn("human_override:", txt, f"{rel} 未注册 human_override")
            m = re.search(r"human_override:\n((?: {4}[^\n]*\n)+)", txt)
            self.assertIsNotNone(m, f"{rel} 的 human_override 块解析失败")
            blk = m.group(1)
            self.assertIn('actor_pattern: "human:*"', blk, f"{rel} 的 actor_pattern 不是 human:*")
            self.assertIn("authority_level: 4", blk, f"{rel} 的 authority_level 不是 4（人侧最高）")

    # ---- 协议面回归（不许因 ops 扩面而动八工具）----
    def test_protocol_eight_tools_unchanged(self):
        with open(SERVER_SRC, encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"^TOOL_FUNCS = \{(.+?)\}$", src, re.S | re.M)
        self.assertIsNotNone(m, "TOOL_FUNCS 未找到")
        names = set(re.findall(r'"(\w+)":', m.group(1)))
        self.assertEqual(names, {"memory_append", "memory_retrieve", "memory_promote",
                                 "memory_tombstone", "memory_verify", "anchor", "scan",
                                 "adjudicate"},
                         "协议面八工具被改动——扩张须走 SPEC 增补（裁定索引 §一 第 9 行）")
        self.assertNotIn("human_override", names, "人侧终裁**不得**进协议面（只能在 ops）")
        rc, log = _run([self.server, "selftest", "--libs-root", self.libs])
        self.assertEqual(rc, 0, log)
        self.assertIn("selftest: 9/9", log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
