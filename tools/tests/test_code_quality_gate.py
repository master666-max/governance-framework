# -*- coding: utf-8 -*-
"""code_quality_gate 自测（03-health S9：守门者自身此前零测试）。
口径：subprocess 真跑 CLI，断言退出码与输出——空转/绕过形态必须红。"""
import os
import subprocess
import sys
import tempfile
import unittest

GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "code_quality_gate.py")


def run_gate(args):
    return subprocess.run([sys.executable, "-X", "utf8", GATE, *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


class TestGateFailClosed(unittest.TestCase):
    def test_no_args_is_rejected_not_passed(self):
        r = run_gate([])
        self.assertEqual(r.returncode, 2, f"空参数必须 rc=2（fail-closed），得 {r.returncode}")

    def test_allow_missing_value_is_usage_error(self):
        r = run_gate(["--allow"])
        self.assertEqual(r.returncode, 2)

    def test_allow_equals_form_is_parsed(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "m.py")
            open(f, "w", encoding="utf-8").write("import thirdparty_xyz\n")
            r = run_gate([f, "--allow=thirdparty_xyz"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # 不带 allow 的同一文件必须红（对照：解析没有静默丢掉名单）
            r2 = run_gate([f])
            self.assertEqual(r2.returncode, 1)


class TestGateBypassForms(unittest.TestCase):
    def test_from_import_alias_system_is_caught(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "m.py")
            open(f, "w", encoding="utf-8").write(
                "from os import system\nsystem('echo hi')\n")
            r = run_gate([f])
            self.assertEqual(r.returncode, 1, "from-import 别名形态不得绕过门⑥")
            self.assertIn("SECURITY", r.stdout)

    def test_dynamic_import_module_hits_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "m.py")
            open(f, "w", encoding="utf-8").write(
                "import importlib\nimportlib.import_module('sneaky_pkg')\n")
            r = run_gate([f])
            self.assertEqual(r.returncode, 1, "import_module 动态导入必须按门④处理")
            self.assertIn("IMPORT", r.stdout)

    def test_clean_file_passes(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "m.py")
            open(f, "w", encoding="utf-8").write("import json\nprint(json.dumps({}))\n")
            r = run_gate([f])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
