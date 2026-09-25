# -*- coding: utf-8 -*-
"""test_docs.py — S6 文档收束的机械判据（C1-C5 · 承载《S6预注册-文档收束-20260923》§2.2）

判据 ↔ 实现映射（预注册条款②）：
  C1 零代号        → test_no_codenames（黑名单 12 词+2 正则；路径例外读 D3 登记表）
  C2 命令可执行    → test_bash_blocks_run（逐块 bash -e 执行 exit 0）
                     + test_runner_discriminates / test_runner_catches_midblock_failure（负向对照）
  C3 结构齐备      → test_structure（D1 三形态×五节 / D2 三路×五要素 / D3 术语表≥20）
  C4 迁移数字可追溯 → test_migration_numbers_traceable（跑 demo 与 D2 引用值比对）
  C5 期望读数核对  → test_expected_readings（附录表逐条回放；豁免口径=耗时/ts/临时路径/ResourceWarning）
C6（人话验收）为治理位人读项，不在本件。

用法: py -X utf8 build/tests/test_docs.py
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, "交付-S1v2-20260923")
D1 = os.path.join(DOCS, "说明书-三形态-20260923.md")
D2 = os.path.join(DOCS, "指南-迁移与装配切换-20260923.md")
D3 = os.path.join(DOCS, "索引与术语-20260923.md")
DEMO = os.path.join(ROOT, "build", "demo_e2e.py")

# —— C1 黑名单（冻结）——
BLACK_WORDS = ["混元", "豆包", "衔尾蛇", "迷深", "线A", "线B", "线C", "线M",
               "DSH", "research-hub", "INCREMENTAL-LOG", "交接包"]
BLACK_RES = [re.compile(r"条目\s*\d+"), re.compile(r"[A-Z]{1,2}-\d{2,3}")]
# —— C5 豁免口径（冻结）——
EXEMPT_LINE = re.compile(r"(\d+(\.\d+)?\s*(ms|s)\b|耗时|T\d{2}:\d{2}:\d{2}|"
                         r"Temp[\\/]|ResourceWarning|at=|ts=)")
BASH_BLOCK = re.compile(r"```bash\n(.*?)```", re.S)
OUT_SNIPPET = 300          # 失败输出摘录长
READINGS = re.compile(r"^\| (\d+) \| `([^`]+)` \| `?([^|`]+?)`? \|\s*$", re.M)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _bash_blocks(text):
    return [b.strip() for b in BASH_BLOCK.findall(text)]


_BASH = []


def _bash_bin():
    """选真 shell：本机 PATH 里的 bash 是 WSL 转发器（实测不可用）——显式定位 Git Bash（缓存）。"""
    if _BASH:
        return _BASH[0]
    cands = [os.environ.get("AUDIT_DOC_BASH"), r"C:/Program Files/Git/bin/bash.exe",
             r"C:/Program Files (x86)/Git/bin/bash.exe", "bash", "sh"]
    for c in cands:
        if not c:
            continue
        try:
            r = subprocess.run([c, "-c", "exit 0"], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            _BASH.append(c)
            return c
    raise RuntimeError("找不到可用 shell（试过 Git Bash 常规路径与组网 sh）")


def _run_block(block):
    """整块交给真 shell（含 &&/cp/rm 等构造）；返回 (exit, 两流合并输出)。

    `-e`（errexit）是**必需**的，不是风格：不带它时块的退出码=**最后一条**命令的退出码，
    块内前序命令失败会被吞成 PASS。实测曾让三条多行块连绿若干波（中间步骤
    「目标目录非空，拒绝覆盖」从未被看见）。
    """
    r = subprocess.run([_bash_bin(), "-e", "-c", block], cwd=ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    return r.returncode, r.stdout


class TestC1NoCodenames(unittest.TestCase):
    def test_no_codenames(self):
        """C1：三文档正文对黑名单零命中；路径例外=在 D3 登记表逐条声明者。"""
        d3 = _read(D3) if os.path.isfile(D3) else ""
        exempt = set(re.findall(r"路径例外[：:]\s*(\S+)", d3))
        hits = []
        for path in (D1, D2, D3):
            if not os.path.isfile(path):
                continue
            for i, line in enumerate(_read(path).splitlines(), 1):
                for w in BLACK_WORDS:
                    if w in line and w not in exempt:
                        hits.append(f"{os.path.basename(path)}:{i} 词[{w}]")
                for rgx in BLACK_RES:
                    for m in rgx.finditer(line):
                        if m.group(0) not in exempt:
                            hits.append(f"{os.path.basename(path)}:{i} 形[{m.group(0)}]")
        self.assertEqual(hits, [], f"零代号命中（未登记豁免）：{hits}")


class TestC2CommandsRun(unittest.TestCase):
    def test_bash_blocks_run(self):
        """C2：三文档全部 bash 块逐块执行 exit 0（块序=D1→D2→D3；块内 `-e` 逐条严判）。"""
        fails = []
        for path in (D1, D2, D3):
            if not os.path.isfile(path):
                continue
            for bi, block in enumerate(_bash_blocks(_read(path)), 1):
                if block.startswith("# no-run:"):
                    continue
                rc, out = _run_block(block)
                if rc != 0:
                    fails.append(f"{os.path.basename(path)} 块{bi}: exit={rc}\n{out[-OUT_SNIPPET:]}")
        self.assertEqual(fails, [], "\n---\n".join(fails))

    def test_runner_discriminates(self):
        """C2 负向对照：故意错误命令必须被判 FAIL（防'没跑'与'跑了没问题'同形）。"""
        rc, _out = _run_block("py -X utf8 build/__不存在__.py")
        self.assertNotEqual(rc, 0, "装置未识别失败命令（判别力失效）")

    def test_runner_catches_midblock_failure(self):
        """C2 负向对照②：块内**非末条**命令失败必须 FAIL。

        本判据自身曾漏这一类：无 errexit 时退出码只等于末条命令，中间步骤失败一律隐身
        ——所以"块跑绿"不等于"块里每条命令都成立"。
        """
        rc, _out = _run_block("py -X utf8 build/__不存在__.py\necho 末条命令成功")
        self.assertNotEqual(rc, 0, "块内前序失败被吞（退出码取自末条命令 ⇒ 门有盲点）")


class TestC3Structure(unittest.TestCase):
    FIVE = ("它是什么", "部署三步", "日常用法", "体检与读数", "边界与已登记项")

    def test_structure(self):
        """C3：D1 三形态×五节；D2 三路×五要素；D3 术语表≥20 条。"""
        d1 = _read(D1)
        for i in (1, 2, 3):
            for k, title in enumerate(self.FIVE, 1):
                self.assertIn(f"### {i}.{k} {title}", d1, f"D1 缺 {i}.{k} {title}")
        d2 = _read(D2)
        for route in ("升格", "降格", "装配切换"):
            self.assertIn(f"## {route}", d2, f"D2 缺路：{route}")
            seg = d2.split(f"## {route}", 1)[1].split("\n## ", 1)[0]
            for el in ("前置", "步骤", "核验", "期望读数", "回退"):
                self.assertIn(el, seg, f"D2 路[{route}] 缺要素：{el}")
        d3 = _read(D3)
        gloss = d3.split("## 二 · 术语表", 1)[1].split("\n## ", 1)[0]   # 只数术语表节内行
        rows = [ln for ln in gloss.splitlines() if ln.startswith("| ") and ln.count("|") >= 3]
        self.assertGreaterEqual(len(rows) - 2, 20, f"D3 术语表不足 20 条（实计 {len(rows) - 2}）")


class TestC4MigrationTraceable(unittest.TestCase):
    def test_migration_numbers_traceable(self):
        """C4：D2 升格段引用的三同读数与演示器实测同源（重跑 demo 比对）。"""
        d2 = _read(D2)
        m = re.search(r"three_same[^`]*`?([0-9a-f]{16})`?", d2)
        self.assertIsNotNone(m, "D2 未引用升格三同读数（不得空写）")
        r = subprocess.run([sys.executable, "-X", "utf8", DEMO], cwd=ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout[-OUT_SNIPPET:])
        import json
        with open(os.path.join(ROOT, "build", "out", "demo", "demo.json"), encoding="utf-8") as f:
            data = json.load(f)
        live = data["segments"]["seg4_promote"]["three_same"]["digest"]
        self.assertEqual(m.group(1), live, f"D2 引用 {m.group(1)} ≠ 实测 {live}")


class TestC5ExpectedReadings(unittest.TestCase):
    def test_expected_readings(self):
        """C5：各文档附录"期望读数表"逐条回放；命中前按豁免口径剔除漂移行。"""
        checked = 0
        for path in (D1, D2, D3):
            if not os.path.isfile(path):
                continue
            text = _read(path)
            if "期望读数表" not in text:
                continue
            for _n, cmd, expect in READINGS.findall(text):
                rc, out = _run_block(cmd)
                self.assertEqual(rc, 0, f"[{cmd}] exit={rc}\n{out[-OUT_SNIPPET:]}")
                clean = EXEMPT_LINE.sub("<x>", out)   # 字段级替换：只漂移字段变占位，行保留
                self.assertIn(expect.strip(), clean, f"[{cmd}] 未含期望读数：{expect.strip()!r}\n{clean[-OUT_SNIPPET:]}")
                checked += 1
        self.assertGreaterEqual(checked, 1, "未找到任何期望读数行（表式不符）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
