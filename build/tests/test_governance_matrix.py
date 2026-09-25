# -*- coding: utf-8 -*-
"""test_governance_matrix.py — S8-8 治理矩阵的**机械判据**（20260923 开工批）

承载《S8工单》S8-8：「扫三形态命令/工具清单 → 对照**矩阵表（冻结在本件内）**→
每格"有入口 or 有登记理由"；负向对照=故意删一条命令须 FAIL」。
矩阵表与 `S8工单` §1.1 同源；工单 §1.1 的「能力签发/撤销」在本件拆成 **8a 签发 / 8b 撤销**
两格（拆开才可判定：服务件有 `grant` 无 `revoke`，合成一格就没法表达半缺）。

两条防线，方向相反：
  · **缺格必红**（`test_every_cell_accounted`）：某格既无入口又无登记理由 ⇒ FAIL；
  · **野命令必红**（`test_no_unregistered_command`）：形态里冒出矩阵没记的命令 ⇒ FAIL
    ——新增/改名命令必须同步矩阵，这就是"防漂移"的那一半。
外加负向对照（`test_negative_control_*`）：人为删掉一条命令，检查器**必须**报错——
否则"矩阵全格合规"可能只是因为检查器根本不认得任何命令。

用法: py -X utf8 build/tests/test_governance_matrix.py
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEAT_SRC = os.path.join(ROOT, "evo-seat", "evo_seat.py")
KB_SRC = os.path.join(ROOT, "build", "kb_template", "tools", "kb.py")
SRV_SRC = os.path.join(ROOT, "build", "l2server", "server.py")

FORMS = ("fused", "kb", "server")
FORM_LABEL = {"fused": "微内核（融合单文件）", "kb": "中库（包内自足）", "server": "共库（L2 服务件）"}

# ── 矩阵（冻结在此）：行=治理操作，列=三形态 ─────────────────────────────
# 值 ∈ ("entry", [命令名…]) —— 该形态必须真的有这些入口
#     ∈ ("registered", 理由, [命令名…可选]) —— 设计上不承载 / 待某工单项，理由必须点名**可追查的出处**
# 理由必须含 `S8-`/`L2-`/`SPEC`/`裁定`/`§`/`读数` 之一（防"以后再说明"式空借口）。
MATRIX = {
    "1 建库/写入/读取/链验证": {
        "fused":   ("entry", ["init", "append", "retrieve", "verify"]),
        "kb":      ("entry", ["add", "import", "query", "verify"]),   # 建库在 make_kb init
        "server":  ("entry", ["memory_append", "memory_retrieve", "memory_verify"])},
    "2 晋升/墓碑": {
        "fused":   ("entry", ["promote", "tombstone"]),
        "kb":      ("entry", ["promote", "tombstone"]),        # S8-1 已落地（20260923 W3d）
        "server":  ("entry", ["memory_promote", "memory_tombstone"])},
    "3 入库锚/出站扫描": {
        "fused":   ("entry", ["anchor", "scan"]),
        "kb":      ("entry", ["anchor", "scan"]),               # S8-1 已落地
        "server":  ("entry", ["anchor", "scan"])},
    "4 三 intent 决策": {
        "fused":   ("entry", ["decide"]),
        "kb":      ("entry", ["decide"]),                        # S8-1 已落地
        "server":  ("entry", ["adjudicate"])},
    "5 质量门": {
        "fused":   ("entry", ["gate"]),
        "kb":      ("registered", "S3 裁定①：门/档位=融合形态机制，不移植；"
                                  "中库体检用 conformance --kb（见 kb.py 头注）"),
        "server":  ("entry", ["gate"])},        # S8-2 已落地：ops gate 转调仓级门，exit 原样透传
    "6 审查档位 G0-G5": {
        "fused":   ("entry", ["level"]),
        "kb":      ("registered", "S3 裁定①：中库设计不承载档位（S8工单 §1.1 同记）"),
        "server":  ("registered", "S3 裁定①：共库设计不承载档位（S8工单 §1.1 同记）")},
    "7 综合审查": {
        "fused":   ("entry", ["audit"]),
        "kb":      ("entry", ["audit"]),                          # S8-1 已落地
        "server":  ("entry", ["audit"])},        # S8-2 已落地：ops audit 逐库巡检（协议面 memory_verify 只管单库）
    "8a 能力签发": {
        "fused":   ("registered", "SPEC §A 豁免声明：融合形态=档位静态权限，无签发面（裁定索引 §一 第 5 行）"),
        "kb":      ("registered", "本地常设能力（L1 单写者），签发面归 S8工单 §1.1 设计不承载"),
        "server":  ("entry", ["grant"])},
    "8b 能力撤销": {
        "fused":   ("registered", "SPEC §A 豁免声明：无令牌可撤（同上）"),
        "kb":      ("registered", "S8-3 已按登记落地：中库无运行时撤销面（CAP 在 tools/kb.py 内声明"
                                  "expires=None），收权=改该声明重发模板；kb.py 头注有本条说明"),
        "server":  ("entry", ["revoke"])},        # S8-3 已落地：入账 capability_revoke + 移出 caps.json
    "9 人侧仲裁 override": {                          # S8-4 已落地（20260923 W3a）
        "fused":   ("entry", ["override"]),
        "kb":      ("entry", ["override"]),
        "server":  ("entry", ["override"])},
    "10 来源审计视图（最小版）": {            # S8-6 已落地：按**完整 actor** 聚合（非首段前缀，理由登记在 project_sources）
        "fused":   ("entry", ["audit"]),       # 融合件不新增子命令——附段挂在 audit 输出里
        "kb":      ("entry", ["sources"]),
        "server":  ("entry", ["sources"])},
    "11 判据注入的生效": {                            # S8-5 大部落地（20260923 W3b）
        "fused":   ("registered", "残留已登记：_trace 在 framework_sha 覆盖的 §5 机制段，"
                                  "改它须走版本闸流程——出处 02-自检读数 §W3b-五"),
        "kb":      ("entry", ["decide"]),                        # S8-5② + S8-1 接线完成
        "server":  ("entry", ["adjudicate"])},
}

_REASON_CITED = re.compile(r"S8-|L2-|SPEC|裁定|§|读数|自检|非治理")

# 豁免面：确实存在、但**不属治理操作**的命令。豁免同样必须给出处——
# 否则"加进豁免表"会变成绕过野命令检查的后门（与恒真判据同族的另一条路）。
EXEMPT = {
    "selftest": "非治理操作：形态内自检诊断（融合件 §8 / 服务件 ops），S8工单 §1.1 矩阵本就不列",
    "stats":    "非治理操作：运营统计；其「仅工具计数、非综合审查」的缺口记在本表第 7 格",
}


# ── 事实面：从源码里扫出各形态真实存在的命令/工具名 ────────────────────────
def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def surface_fused():
    return set(re.findall(r'sp\.add_parser\(\s*"([a-z][a-z0-9_]*)"', _read(SEAT_SRC)))


def surface_kb():
    src = _read(KB_SRC)
    return set(re.findall(r'sp\.add_parser\(\s*"([a-z][a-z0-9_]*)"', src))


def surface_server():
    src = _read(SRV_SRC)
    m = re.search(r"^TOOL_FUNCS = \{(.+?)\}$", src, re.S | re.M)
    tools = set(re.findall(r'"([a-z_]+)":', m.group(1))) if m else set()
    mo = re.search(r'for name in \(([^)]*)\):', src)
    ops = set(re.findall(r'"([a-z]+)"', mo.group(1))) if mo else set()
    return tools | ops


SURFACE = {"fused": surface_fused, "kb": surface_kb, "server": surface_server}


def audit_cells(matrix, surface):
    """→ [(行, 形态, 问题)]：该格既无入口又无登记理由，或 entry 格的命令实际不在。"""
    bad = []
    for row, cells in matrix.items():
        for form in FORMS:
            cell = cells.get(form)
            if cell is None:
                bad.append((row, form, "空格：既无入口也无登记理由"))
                continue
            if cell[0] == "entry":
                missing = [c for c in cell[1] if c not in surface[form]]
                if missing:
                    bad.append((row, form, f"声明有入口但实际不在位：{missing}"))
            elif cell[0] == "registered":
                if not cell[1] or not _REASON_CITED.search(cell[1]):
                    bad.append((row, form, "登记理由缺可追查出处（须点名 S8-/L2-/SPEC/裁定/§）"))
            else:
                bad.append((row, form, f"未知格类型：{cell[0]}"))
    return bad


def audit_orphans(matrix, surface, exempt=None):
    """→ [(形态, 命令)]：形态里实际存在、但矩阵任何一格都没提到的命令（野命令）。

    `exempt` 里的名字算"已豁免"（须带出处，见 `test_exempt_entries_are_cited`）；
    默认用模块级 EXEMPT。传 `{{}}` 即关闭豁免——负向对照用。
    """
    exempt = EXEMPT if exempt is None else exempt
    mentioned = set(exempt)
    for cells in matrix.values():
        for cell in cells.values():
            if cell[0] == "entry":
                mentioned |= set(cell[1])
            if len(cell) > 2:
                mentioned |= set(cell[2])
    return [(f, c) for f in FORMS for c in sorted(surface[f]) if c not in mentioned]


# ── S8-7：读者版表格（**由矩阵渲染，不手抄**）────────────────────────────
D1 = os.path.join(ROOT, "交付-S1v2-20260923", "说明书-三形态-20260923.md")
ROW_ORDER = re.compile(r"^(\d+)([a-z]?)\s")


def rows_sorted(matrix=None):
    """行序：按编号数值 + 字母后缀（1,2,…,8a,8b,9,10,11）——与打印/文档同一套序。"""
    matrix = MATRIX if matrix is None else matrix
    return sorted(matrix, key=lambda r: (int(ROW_ORDER.match(r).group(1)),
                                         ROW_ORDER.match(r).group(2)))


def render_reader_table(matrix=None):
    """→ markdown 表：说明书 §4.1 直接嵌这段文本（`test_manual_reader_table_in_sync` 逐字比对）。

    ＋=该形态有真入口（命令名如实列出）；○=设计上不承载，格内给登记理由。
    理由必须留在表里——读者问"为什么中库没有撤销命令"时，文档要能自己答，
    而不是把人支去翻工单。
    """
    matrix = MATRIX if matrix is None else matrix
    out = ["| 治理操作 | " + " | ".join(FORM_LABEL[f] for f in FORMS) + " |",
           "|---|---|---|---|"]
    for row in rows_sorted(matrix):
        cells = []
        for f in FORMS:
            c = matrix[row][f]
            cells.append("＋ " + " / ".join(c[1]) if c[0] == "entry" else "○ " + c[1])
        out.append("| " + " | ".join([row] + cells) + " |")
    return "\n".join(out)


class TestGovernanceMatrix(unittest.TestCase):
    def test_matrix_is_complete_grid(self):
        """每行必须三格齐全（不许漏列某形态）。"""
        for row, cells in MATRIX.items():
            self.assertEqual(set(cells), set(FORMS), f"{row} 格不齐：{sorted(cells)}")

    def test_every_cell_accounted(self):
        bad = audit_cells(MATRIX, {f: SURFACE[f]() for f in FORMS})
        self.assertEqual(bad, [], "\n".join(f"{r} × {FORM_LABEL[f]}：{why}" for r, f, why in bad))

    def test_no_unregistered_command(self):
        """新增/改名命令必须同步矩阵——这条是防漂移的正手。"""
        surf = {f: SURFACE[f]() for f in FORMS}
        orphans = audit_orphans(MATRIX, surf)
        self.assertEqual(orphans, [],
                         f"矩阵未记录的命令：{orphans}（新命令须在 MATRIX 里占一格并给出处）")

    def test_surface_actually_nonempty(self):
        """哨兵不裸：扫得出命令才算扫描器接上了（扫到空集会让更多检查假绿）。"""
        surf = {f: SURFACE[f]() for f in FORMS}
        for f in FORMS:
            self.assertGreaterEqual(len(surf[f]), 5, f"{FORM_LABEL[f]} 只扫出 {sorted(surf[f])}")
        self.assertIn("override", surf["fused"] & surf["kb"] & surf["server"])

    def test_negative_control_removed_command(self):
        """负向对照①：人为删一条命令 ⇒ 检查器必须报错（否则"全格合规"是空的）。"""
        surf = {f: SURFACE[f]() for f in FORMS}
        for f in FORMS:
            surf[f] = surf[f] - {"override"}
        bad = audit_cells(MATRIX, surf)
        self.assertTrue(any("人侧仲裁" in r for r, _f, _w in bad),
                        f"删掉三形态 override 后检查器没报错：{bad}")

    def test_negative_control_new_command(self):
        """负向对照②：凭空多一条命令 ⇒ 野命令检查必须报错。"""
        surf = {f: SURFACE[f]() for f in FORMS}
        surf["kb"] = surf["kb"] | {"selfdestruct"}
        orphans = audit_orphans(MATRIX, surf, exempt={})     # 关豁免：证明抓的是"没记录"而不是"没豁免"
        self.assertIn(("kb", "selfdestruct"), orphans, f"野命令未被抓：{orphans}")
        # 且豁免表本身不会把真野命令放过去
        orphans2 = audit_orphans(MATRIX, surf)
        self.assertIn(("kb", "selfdestruct"), orphans2, f"带豁免表时野命令被放过：{orphans2}")

    def test_negative_control_vacuous_reason(self):
        """负向对照③：登记理由若不给出处 ⇒ 必须报错（防"以后再说明"）。"""
        surf = {f: SURFACE[f]() for f in FORMS}
        fake = {k: dict(v) for k, v in MATRIX.items()}
        fake["2 晋升/墓碑"]["kb"] = ("registered", "以后再说")
        bad = audit_cells(fake, surf)
        self.assertTrue(any("可追查出处" in w for _r, _f, w in bad),
                        f"空借口竟然放行：{bad}")

    def test_exempt_entries_are_cited(self):
        """豁免表不是后门：每条必须给可追查出处，且名字确实存在于某形态表面。"""
        surf = {f: SURFACE[f]() for f in FORMS}
        real = set().union(*surf.values())
        for name, why in EXEMPT.items():
            self.assertTrue(_REASON_CITED.search(why), f"豁免 {name} 无出处：{why}")
            self.assertIn(name, real, f"豁免 {name} 已成僵尸（各形态都没有这条命令，应删登记）")
        for f in FORMS:                      # 豁免不得顺手盖掉真缺口
            for cell in MATRIX.values():
                if cell[f][0] == "entry":
                    self.assertFalse(set(cell[f][1]) & set(EXEMPT),
                                     f"入口格的命令不得同时出现在豁免表：{cell}")

    def test_current_landed_items(self):
        """本批已落地两件的现状锁定：override 三格皆入口；prereg 仅服务件成入口。"""
        ov = MATRIX["9 人侧仲裁 override"]
        self.assertTrue(all(ov[f][0] == "entry" for f in FORMS), ov)
        pr = MATRIX["11 判据注入的生效"]
        self.assertEqual(pr["server"][0], "entry")
        self.assertEqual(pr["fused"][0], "registered", "融合件 prereg 仍是登记残留，不得静默算通过")

    def test_print_matrix_for_humans(self):
        """把读者版表格打到 stdout（说明书 §4.1 嵌的就是这段文本，一条都不手抄）。"""
        tbl = render_reader_table()
        print("\n治理矩阵（S8-8 冻结表 · ＋=有入口 ○=有登记理由）\n" + tbl)
        self.assertEqual(len(tbl.splitlines()), len(MATRIX) + 2)

    def test_manual_reader_table_in_sync(self):
        """S8-7：说明书 §4.1 的表格必须与 MATRIX **逐字**同源。

        为什么钉逐字：文档表格一旦手抄，改矩阵的人不会想起去改文档（本仓 DR 面一堆此类漂移）。
        钉住之后，改矩阵=改文档，一个提交里两件事必须同时发生，否则本判据红。
        """
        self.assertIn(render_reader_table(), _read(D1),
                      "说明书 §4.1 表格与 MATRIX 不同源 ⇒ 跑 `test_print_matrix_for_humans` 取表回填")

    def test_manual_section_declares_three_channels(self):
        """S8-7：说明书「治理操作」节必须覆盖人侧三通道＋治理位外置（缺一条=文档没收口）。"""
        doc = _read(D1)
        seg = doc.split("## 四 · 治理操作", 1)
        self.assertEqual(len(seg), 2, "说明书缺 §四·治理操作")
        body = seg[1]
        for needle in ("终裁", "撤销", "判据", "治理位在库外", "验证不能自证", "默认不放行"):
            self.assertIn(needle, body, f"§四 未写到：{needle}")

    def test_negative_control_reader_table_drift(self):
        """负向对照④：矩阵改一格而文档未跟 ⇒ 同步判据必须报错（否则它是恒真的装饰）。"""
        fake = {k: dict(v) for k, v in MATRIX.items()}
        fake["9 人侧仲裁 override"] = dict(fake["9 人侧仲裁 override"])
        fake["9 人侧仲裁 override"]["kb"] = ("entry", ["override", "arbitrate"])
        drifted = render_reader_table(fake)
        self.assertNotEqual(drifted, render_reader_table())
        self.assertNotIn(drifted, _read(D1), "矩阵变了、文档没变，同步判据却仍判同源 ⇒ 判别力失效")


if __name__ == "__main__":
    unittest.main(verbosity=2)
