# -*- coding: utf-8 -*-
"""test_boot_self.py — 自举账本恢复路径测试（P1 欠账清偿 · 20260924）

boot_self.py 此前六符号零测试（docs批 H1：恰是 P0 同域的恢复面）。
本件守的契约：
  ① sync 幂等（同仓二跑新增 0）；
  ② status 全覆盖/缺失判定正确（新提交后必须报缺失）；
  ③ rebuild 不删除（原库改名留档；二次 rebuild 拒绝覆盖备份——fail-closed）；
  ④ 坏 payload fail-closed 计数（不吞）；
  ⑤ git 不可用 → SystemExit（不许静默空过）。
运行：cd audit-kit/tests && py -X utf8 -m unittest test_boot_self
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))          # audit-kit/
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "ledger"))

import boot_self                                    # noqa: E402


def _run(args, cwd=None):
    r = subprocess.run([sys.executable, "-X", "utf8", *args],
                       capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    return r.returncode, r.stdout + r.stderr


class TempGitRepo:
    """最小 git 仓：init + 一笔提交（隔离于真实审计区）。"""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="bootself_repo_")
        subprocess.run(["git", "init", "-q"], cwd=self.dir, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.dir, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.dir, check=True)
        with open(os.path.join(self.dir, "f.txt"), "w", encoding="utf-8") as f:
            f.write("v1\n")
        subprocess.run(["git", "add", "f.txt"], cwd=self.dir, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=self.dir, check=True)

    def commit(self, msg="c2"):
        with open(os.path.join(self.dir, "f.txt"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        subprocess.run(["git", "add", "f.txt"], cwd=self.dir, check=True)
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=self.dir, check=True)


class TestBootSelf(unittest.TestCase):
    def setUp(self):
        self.repo = TempGitRepo()
        self.tmp = tempfile.mkdtemp(prefix="bootself_db_")
        self.db = os.path.join(self.tmp, "boot.db")
        self.patches = [mock.patch.object(boot_self, "AUD", self.repo.dir),
                        mock.patch.object(boot_self, "DB", self.db)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_sync_idempotent(self):
        boot_self.cmd_sync()
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            boot_self.cmd_sync()
        self.assertIn("本次新增 0", buf.getvalue())

    def test_status_missing_detected(self):
        boot_self.cmd_sync()
        self.repo.commit("c2-later")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            boot_self.cmd_status()
        self.assertIn("缺失 1", buf.getvalue())

    def test_rebuild_keeps_backup_and_refuses_overwrite(self):
        boot_self.cmd_sync()
        self.assertTrue(os.path.isfile(self.db))
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            boot_self.cmd_rebuild()
        bak = self.db + ".pre-v2.bak"
        self.assertTrue(os.path.isfile(bak), "原库必须留档不删除")
        self.assertTrue(os.path.isfile(self.db), "重建后新库在位")
        with self.assertRaises(SystemExit):          # 二次 rebuild：拒绝覆盖备份
            boot_self.cmd_rebuild()

    def test_bad_payload_counted_fail_closed(self):
        boot_self.cmd_sync()
        import sqlite3
        con = sqlite3.connect(self.db)
        # 坏 payload 行：不 经 open()（开库即验会按设计拒坏库）——直连构造，
        # 专测 recorded_hashes 的 fail-closed 计数不吞错。
        con.execute(
            "INSERT INTO events (ts, actor, kind, payload, prev_hash, self_hash) "
            "VALUES ('t','x','y','{broken-json','ff','ff')")
        con.commit()
        from ledger import Ledger
        led = Ledger(con)
        have, bad = boot_self.recorded_hashes(led)
        self.assertEqual(bad, 1)                     # 恰 1 条坏行被计数
        self.assertEqual(len(have), 1)               # 好行照常入集
        con.close()

    def test_git_unavailable_refuses(self):
        boot_self.AUD = tempfile.mkdtemp(prefix="bootself_nogit_")   # 非 git 目录
        with self.assertRaises(SystemExit):
            boot_self.cmd_sync()


if __name__ == "__main__":
    unittest.main()
