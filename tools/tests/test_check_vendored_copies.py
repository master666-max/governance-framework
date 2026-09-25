# -*- coding: utf-8 -*-
"""test_check_vendored_copies.py — 副本族校验器的裁决器测试（20260925 重构第一轮 E-6）

被测件：tools/check_vendored_copies.py（FAMILIES 可注入 → 全部用 tempfile 造族，不触真副本）。
四例：齐=0；漂=1；缺件=1；空族表=2。期望值全部来自真实运行（D 步纪律）。
"""
import importlib.util
import os
import sys
import tempfile
import unittest

_TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "check_vendored_copies.py")


def _load_with_families(families, tmp):
    """以注入的族表载入校验器模块（在 tmp 内造物，仓根指向 tmp）。"""
    spec = importlib.util.spec_from_file_location("chk_" + str(id(families)), _TOOL)
    mod = importlib.util.module_from_spec(spec)
    ns = {"__name__": "not_main_yet", "__file__": _TOOL}
    code = open(_TOOL, encoding="utf-8").read()
    exec(compile(code, _TOOL, "exec"), ns)
    ns["FAMILIES"] = families
    ns["_ROOT"] = tmp
    return ns


class TestCopyCheckerVerdicts(unittest.TestCase):
    def _run(self, families, layout):
        tmp = tempfile.mkdtemp(prefix="copychk_")
        try:
            for rel, content in layout.items():
                p = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(content)
            ns = _load_with_families(families, tmp)
            return ns["main"]()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_aligned_family_exits_zero(self):
        rc = self._run({"族A": ["a/f.py", "b/f.py"]},
                       {"a/f.py": b"same", "b/f.py": b"same"})
        self.assertEqual(rc, 0)

    def test_drifted_family_exits_one(self):
        rc = self._run({"族A": ["a/f.py", "b/f.py"]},
                       {"a/f.py": b"same", "b/f.py": b"drift"})
        self.assertEqual(rc, 1)

    def test_missing_member_exits_one(self):
        rc = self._run({"族A": ["a/f.py", "ghost/f.py"]},
                       {"a/f.py": b"same"})
        self.assertEqual(rc, 1)

    def test_empty_families_exits_two(self):
        rc = self._run({}, {})
        self.assertEqual(rc, 2)

    def test_real_repo_families_aligned_now(self):
        """真仓族表现跑必须齐——这是本器在当前 HEAD 下的常态断言（若红=副本已漂，先修漂移再改族表）。"""
        ns = {"__name__": "not_main_yet", "__file__": _TOOL}
        exec(compile(open(_TOOL, encoding="utf-8").read(), _TOOL, "exec"), ns)
        self.assertEqual(ns["main"](), 0)


if __name__ == "__main__":
    unittest.main()
