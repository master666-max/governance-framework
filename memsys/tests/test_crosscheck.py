# -*- coding: utf-8 -*-
"""test_crosscheck.py — 双包对拍工具的不变量测试（tools/tools_crosscheck.py）
守的契约：双包合并态脚本 exit 0 / P9 隔离违例必报 文件:行号 / F3 kind 漂移必 FAIL。
工具以 exec 载入独立命名空间——质量门依赖白名单不含工具名，测试不可包式导入它。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("..", "../../audit-kit/core", "../../audit-kit/ledger"):
    p = os.path.normpath(os.path.join(_HERE, sub))
    if p not in sys.path: sys.path.insert(0, p)

from bridge import KINDS                                        # noqa: E402

_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
_TOOL = os.path.join(_ROOT, "tools", "tools_crosscheck.py")
_YML = os.path.join(_ROOT, "memsys", "kinds.yml")


def _load_tool() -> dict:
    """对拍工具源码 exec 进独立命名空间（__file__ 指向工具真实路径，供自豁免用）。"""
    with open(_TOOL, encoding="utf-8") as f:
        src = f.read()
    ns: dict = {"__file__": _TOOL, "__name__": "tools_crosscheck"}
    exec(compile(src, _TOOL, "exec"), ns)   # sec-exempt: 载入对象=本仓 tracked 工具文件（非外部输入）
    return ns


def _tmpdir() -> str:
    return tempfile.mkdtemp(prefix="crosscheck_t_")


def _write(tmp: str, name: str, text: str) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _yml_text(declared) -> str:
    """构造 kinds.yml 夹具：仅 declared 里的 kind 是真声明（2 空格 `name:` 行）。
    夹具的注释与说明文本刻意包含全部 KINDS 名——若解析器按子串计数则永远
    "无缺失"，下面的 FAIL 预期用例会当场抓出。"""
    all_names = "、".join(sorted(KINDS))
    lines = ["# 测试夹具（说明提及全部 kind 名：" + all_names + "，不算声明）",
             "version: 1", "kinds:"]
    for k in sorted(declared):
        lines += [f"  {k}:",
                  f'    description: "说明行提及 {all_names} 不算声明"',
                  "    authority_level: 1"]
    return "\n".join(lines) + "\n"


TOOL = _load_tool()


class TestScript(unittest.TestCase):
    def test_script_exit_zero_three_pass(self):
        """不变量：双包合并态三项对拍当前全过——exit 0 且恰三行 [PASS]（准入门常态）。"""
        r = subprocess.run([sys.executable, "-X", "utf8", _TOOL],
                           capture_output=True, timeout=120, cwd=_ROOT)
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertEqual(r.returncode, 0,
                         f"stdout={out}\nstderr={r.stderr.decode('utf-8', errors='replace')}")
        self.assertEqual(out.count("[PASS]"), 3)
        self.assertNotIn("[FAIL]", out)

    def test_dual_chain_one_db_two_packages(self):
        """不变量：同一 SQLite 两包接力 append，链自 genesis 无缝衔接且重放通过（一条真相链）。"""
        tmp = _tmpdir()
        try:
            ok, detail = TOOL["check_dual_chain"](tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(ok, detail)


class TestIsolation(unittest.TestCase):
    def test_isolation_flags_dotted_memsys_import(self):
        """不变量：P9 隔离破坏（宿主包导入 memsys.bridge）必被抓，且报 文件:行号。"""
        tmp = _tmpdir()
        try:
            _write(tmp, "fake_host.py", "from memsys.bridge import MemoryLedger\n")
            ok, detail = TOOL["check_isolation"](tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(ok, detail)
        self.assertIn("fake_host.py:1", detail)

    def test_isolation_flags_injection_bare_names(self):
        """不变量：sys.path 注入式裸名导入（本仓惯用面）同样视为 memsys 符号违例。"""
        tmp = _tmpdir()
        try:
            _write(tmp, "injected.py", "import bridge\nfrom engine import decision\n")
            ok, detail = TOOL["check_isolation"](tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(ok, detail)
        self.assertIn("injected.py:1 import bridge", detail)
        self.assertIn("injected.py:2 from engine import", detail)

    def test_isolation_passes_clean_framework_imports(self):
        """不变量：框架公开面导入（gov_types/ledger 等白名单面）不误报。"""
        tmp = _tmpdir()
        try:
            _write(tmp, "clean.py", "import os\nfrom gov_types import Capability\n"
                                    "from ledger import Ledger\n")
            ok, detail = TOOL["check_isolation"](tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(ok, detail)

    def test_isolation_passes_on_real_auditkit_tree(self):
        """不变量：当前真实 audit-kit 树（除工具精确自豁免）零 memsys 依赖=P9 现势证据。"""
        ok, detail = TOOL["check_isolation"](os.path.join(_ROOT, "audit-kit"))
        self.assertTrue(ok, detail)
        self.assertFalse(detail.startswith("scanned=0"), "扫描空转=假绿")


class TestKinds(unittest.TestCase):
    def test_kinds_fail_when_kind_missing_from_yml(self):
        """不变量：桥内 kind 未在 yml 声明（F3 漂移）必 FAIL 且逐个报缺——缺一即拒。"""
        tmp = _tmpdir()
        try:
            yml = _write(tmp, "kinds.yml", _yml_text({"memory_adjudicate"}))
            ok, detail = TOOL["check_kinds"](yml)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(ok, detail)
        expected_missing = [k for k in KINDS if k != "memory_adjudicate"]
        for k in expected_missing:
            self.assertIn(k, detail)      # 名字在注释/描述里出现过的也必须报缺

    def test_kinds_fail_on_empty_kinds_block(self):
        """不变量：kinds: 空块=全缺——解析器不许把空声明当全过（防空转假绿）。"""
        tmp = _tmpdir()
        try:
            yml = _write(tmp, "kinds.yml", "version: 1\nkinds:\n")
            ok, detail = TOOL["check_kinds"](yml)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(ok, detail)
        for k in KINDS:
            self.assertIn(k, detail)

    def test_kinds_extra_host_kinds_do_not_fail(self):
        """不变量：检查方向单向 KINDS⊆yml——yml 宿主开放集多声明不罚。"""
        tmp = _tmpdir()
        try:
            yml = _write(tmp, "kinds.yml", _yml_text(set(KINDS) | {"host_extension"}))
            ok, detail = TOOL["check_kinds"](yml)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(ok, detail)

    def test_kinds_pass_on_real_yml(self):
        """不变量：现势 kinds.yml 与 bridge.KINDS 双侧声明一致（当前无 F3 漂移）。"""
        ok, detail = TOOL["check_kinds"](_YML)
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
