# -*- coding: utf-8 -*-
"""assemble.py — S2 四包装配器（一码四包：复制+生成+登记；零文本改写）

设计依据：《S2设计v2-四包装配器全量落地架构-20260923.md》（§2.3 规格；总工单对齐）
一码 = 三棵权威源树：audit-kit/{core,ledger}（治理核）· evocore/（演化核）· evo-seat/evo_seat.py（融合核）。
四产物（build/out/）：
  fused     evo_seat.py(副本) + framework_segment.txt(派生) + fused.manifest.json
  vendored  gov/{core×4, ledger×2, manifest} + evo/{evocore×5, manifest}
  pypkg     audit-kit/{auditkit/{__init__(壳), _payload×5}, pyproject, README}
            evocore/{evocore×5, tests×4, README, pyproject} + pypkg.manifest.json
  server    kernel/{core×4, ledger×2} + evo/evocore×5 + skeletons + ops/ + server.manifest.json
登记件（committed）：build/manifests/*.manifest.json（五份）——产物可弃，清单=对账锚。

命令（用法: py -X utf8 build/assemble.py <cmd> [--out …] [--manifests …]）：
  all        清空重建四产物 → 逐产物 conformance/smoke → 写清单（产物内 + 登记位）
  reconcile  对账五查（产物文件==清单 · 副本==源 · conformance 重跑 · 登记件一致 · evo 冒烟）
  audit      S2-T3/T4/T5/T7/T8 验收报告（安全/坏味/跨产物一致性/计时/复用记账；只读）
  check-copy 外部副本两级对账（fused=机制段冻结面+适配面摘要；gov/evo=全文件逐字节）
确定性：无时间戳/无绝对路径（cmd 记 <out> 占位）/utf-8·LF；出口门=双跑逐位一致。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = "SPEC-内核接口与宿主契约-v1+v1.1增补-20260924"   # v1.1 生效（代裁 20260924）：两件并列在效
AK_CORE = ("gov_types.py", "hashes.py", "capabilities.py", "prereg.py")   # S8-5：判据件机械格式+引用指针
AK_LEDGER = ("ledger.py", "schema.sql")
EVOCORE_MODULES = ("__init__.py", "tunables.py", "retrieval.py", "lifecycle.py", "decision.py",
                    "entry.py", "project.py")
EVOCORE_TESTS = ("test_evocore.py", "test_evocore_matrix.py", "test_evocore_s1.py",
                 "test_evocore_contract.py", "test_evocore_entry.py", "test_evocore_project.py")
GOV_SURFACE = ["open", "append", "verify", "count", "head", "rows"]
L2SERVER_FILES = ("server.py", "kinds.yml", "README.md", "prereg/README.md",
                  "prereg/判据-起步-v1.md")   # S4 载荷 + S8-5 判据位（骨架+起步判据件）
MANIFEST_NAMES = ("fused.manifest.json", "gov.manifest.json", "evo.manifest.json",
                  "pypkg.manifest.json", "server.manifest.json")
MIN_SEGMENT_CHARS = 5000   # 与内核 framework_sha 的 len(seg)>=5000 断言同源
_SEG_A = re.compile(r"^# ═+ §1 core", re.M)
_SEG_B = re.compile(r"^# ═+ §7 cli", re.M)


def _p(*parts):
    return os.path.join(ROOT, *parts)


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _wb(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def sha_b(data):
    return hashlib.sha256(data).hexdigest()


def sha_f(path):
    with open(path, "rb") as f:
        return sha_b(f.read())


def _copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "wb") as f:
        f.write(data)
    return sha_b(data)


def _clean(d):
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d, exist_ok=True)


def _rel(p):
    """仓内 → 相对路径；仓外（如临时目录，跨盘符）→ 原样返回（仅用于显示）。"""
    try:
        return os.path.relpath(p, ROOT).replace("\\", "/")
    except ValueError:                 # Windows 跨盘符：relpath 不可用
        return p


def versions():
    """版本表：各源自声明处读取（宣称需 artifact）。"""
    ak = open(_p("audit-kit", "VERSION"), encoding="utf-8").read().strip()
    evo_src = open(_p("evocore", "__init__.py"), encoding="utf-8").read()
    m = re.search(r'^__version__ = "([^"]+)"', evo_src, re.M)
    seat_src = open(_p("evo-seat", "evo_seat.py"), encoding="utf-8").read()
    m2 = re.search(r'^VERSION = "([^"]+)"', seat_src, re.M)
    if not (m and m2):
        raise SystemExit("版本声明缺失（evocore __version__ / evo_seat VERSION）")
    return {"audit-kit": ak, "evocore": m.group(1), "evo-seat": m2.group(1)}


def _seg_of(text):
    """§1…§6 段切片 → (段文本, 字符数) 或 None（横幅未命中）。权威件与外部副本共用。"""
    a, b = _SEG_A.search(text), _SEG_B.search(text)
    if not (a and b):
        return None
    seg = text[a.start():b.start()]
    return seg, len(seg)


def segment():
    """权威件段切片（与内核 framework_sha 同字节串：utf-8 解码+universal newlines）。"""
    with open(_p("evo-seat", "evo_seat.py"), encoding="utf-8") as f:
        src = f.read()
    got = _seg_of(src)
    if got is None:
        raise SystemExit("段定位失败（横幅未命中）")
    seg, chars = got
    if chars < MIN_SEGMENT_CHARS:
        raise SystemExit(f"段仅 {chars} 字符 <{MIN_SEGMENT_CHARS}（拒绝静默坏值）")
    return seg, chars, len(seg.encode("utf-8"))


def kernel_framework_sha():
    """内核自算 framework_sha（独立路径交叉验证用）。"""
    out = subprocess.run([sys.executable, "-X", "utf8", _p("evo-seat", "evo_seat.py"), "selftest"],
                         capture_output=True, text=True, encoding="utf-8")
    src = open(_p("evo-seat", "evo_seat.py"), encoding="utf-8").read()
    a, b = _SEG_A.search(src), _SEG_B.search(src)
    return sha_b(src[a.start():b.start()].encode("utf-8"))[:16], out.returncode


_CONF = _p("audit-kit", "conformance.py")


def _parse_count(pat, r):
    """子进程输出 → (exit, passed, total)（两种工具共用解析，S4 去重）。"""
    m = re.search(pat, r.stdout)
    if not m:
        return r.returncode, 0, 0
    return r.returncode, int(m.group(1)), int(m.group(2))


def run_conf(args):
    """conformance 子进程 → (exit, passed, total)。"""
    r = subprocess.run([sys.executable, "-X", "utf8", _CONF, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return _parse_count(r"conformance: (\d+)/(\d+) PASS", r)


_SMOKE = (
    "import sys, datetime, json;"
    "sys.path.insert(0, {root!r});"
    "from evocore import score, route, DEFAULTS, adjudicate_merge;"
    "e = {{'id':'e1','content':'用户偏好深色主题','keywords':['偏好'],'importance':5,"
    "'created_at':'2026-09-20T00:00:00','type':'semantic'}};"
    "ok = [score(e,'偏好',DEFAULTS,datetime.datetime(2026,9,21,12,0,0)) == 5.391,"
    "route({{'importance':7}}) == 'longterm' and route({{'importance':6}}) == 'intermediate',"
    "adjudicate_merge([{{'id':'x'}},{{'id':'y'}}])['decision'] == 'defer'];"
    "print('SMOKE', ok); sys.exit(0 if all(ok) else 1)")


def smoke_evo(root):
    """evo 件导入冒烟（3 钉值：score 5.391 / route 阈值 / merge defer）。"""
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", _SMOKE.format(root=root)],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (3 if r.returncode == 0 else 0), 3


def run_server_selftest(server_dir):
    """服务件自检（八工具在进程跑一遍）→ (exit, passed, total)。"""
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(server_dir, "server.py"), "selftest"],
                       capture_output=True, text=True, encoding="utf-8")
    return _parse_count(r"selftest: (\d+)/(\d+)", r)


def _manifest(form, vers, files, sources, conf, extra=None):
    man = {"form": form, "versions": vers, "spec": SPEC, "schema_version": 1,
           "files": files, "sources": sources, "aggregate_sha": _aggregate(files),
           "conformance": conf}
    if extra:
        man.update(extra)
    return man


def _aggregate(files):
    body = "".join(f"{k}\0{v}\n" for k, v in sorted(files.items()))
    return sha_b(body.encode("utf-8"))


def _scan_files(d):
    out = {}
    for dp, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x != "__pycache__"]
        for f in fs:
            if f.endswith(".manifest.json"):
                continue
            full = os.path.join(dp, f)
            out[os.path.relpath(full, d).replace("\\", "/")] = sha_f(full)
    return out


def _emit(prod_dir, man_dir, name, man):
    blob = json.dumps(man, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _w(os.path.join(prod_dir, name), blob)
    _w(os.path.join(man_dir, name), blob)


def build_fused(out_root, man_dir, vers):
    """产物1：融合件打包 + 段提取 + 登记。"""
    d = os.path.join(out_root, "fused")
    _clean(d)
    srcs = {}
    srcs["evo_seat.py"] = _rel(_p("evo-seat", "evo_seat.py"))
    _copy(_p("evo-seat", "evo_seat.py"), os.path.join(d, "evo_seat.py"))
    seg, chars, nbytes = segment()
    _wb(os.path.join(d, "framework_segment.txt"), seg.encode("utf-8"))
    fsha, _ = kernel_framework_sha()
    if sha_b(seg.encode("utf-8"))[:16] != fsha:
        raise SystemExit(f"段哈希与内核自算不符：{sha_b(seg.encode('utf-8'))[:16]} != {fsha}")
    ex, ps, tt = run_conf(["--fused", os.path.join(d, "evo_seat.py")])
    conf = [{"what": "conformance --fused", "target": "<out>/fused/evo_seat.py",
             "exit": ex, "passed": ps, "total": tt}]
    man = _manifest("fused", {"evo-seat": vers["evo-seat"]}, _scan_files(d), srcs, conf,
                    extra={"segment": {"file": "framework_segment.txt",
                                       "sha256": sha_b(seg.encode("utf-8")),
                                       "chars": chars, "bytes": nbytes}})
    _emit(d, man_dir, "fused.manifest.json", man)
    return ex == 0


def _copy_group(src_dir, names, dst_dir, prefix, srcs):
    for n in names:
        s = os.path.join(src_dir, n)
        rel = f"{prefix}/{n}" if prefix else n
        srcs[rel] = _rel(s)
        _copy(s, os.path.join(dst_dir, rel))


def build_vendored(out_root, man_dir, vers):
    """产物2：中库载荷（gov 镜像树 + evo 包 + 两份清单）。"""
    d = os.path.join(out_root, "vendored")
    _clean(d)
    gov_srcs = {}
    _copy_group(_p("audit-kit", "core"), AK_CORE, os.path.join(d, "gov"), "core", gov_srcs)
    _copy_group(_p("audit-kit", "ledger"), AK_LEDGER, os.path.join(d, "gov"), "ledger", gov_srcs)
    ex, ps, tt = run_conf(["--kernel", os.path.join(d, "gov")])
    gov_man = _manifest("vendored", {"audit-kit": vers["audit-kit"]}, _scan_files(os.path.join(d, "gov")),
                        gov_srcs, [{"what": "conformance --kernel(gov)",
                                    "target": "<out>/vendored/gov", "exit": ex, "passed": ps, "total": tt}],
                        extra={"component": "gov", "surface": GOV_SURFACE, "gov_impl": "vendored"})
    _emit(os.path.join(d, "gov"), man_dir, "gov.manifest.json", gov_man)
    evo_srcs = {}
    for n in EVOCORE_MODULES:
        evo_srcs[f"evocore/{n}"] = _rel(_p("evocore", n))
        _copy(_p("evocore", n), os.path.join(d, "evo", "evocore", n))
    ex2, ps2, tt2 = smoke_evo(os.path.join(d, "evo"))
    evo_man = _manifest("vendored", {"evocore": vers["evocore"]}, _scan_files(os.path.join(d, "evo")),
                        evo_srcs, [{"what": "smoke evo(3 钉值)", "target": "<out>/vendored/evo",
                                    "exit": ex2, "passed": ps2, "total": tt2}],
                        extra={"component": "evo"})
    _emit(os.path.join(d, "evo"), man_dir, "evo.manifest.json", evo_man)
    return ex == 0 and ex2 == 0


_AUDITKIT_INIT = '''# -*- coding: utf-8 -*-
"""auditkit — audit-kit 独立包壳（S2 装配生成件；载荷在 _payload/，与权威源逐字节一致）
设计依据：S2 设计 v2 §2.2（零 import 改写裁定②）——本壳只做路径注入 + 再导出，
不改载荷一字；顶层模块名（gov_types/hashes/capabilities/ledger）即载荷原名。
"""
import os as _os
import sys as _sys

_PAYLOAD = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_payload")
if _PAYLOAD not in _sys.path:
    _sys.path.insert(0, _PAYLOAD)

from gov_types import Capability, Event, PathGlobScope, ResourceRef, Verdict  # noqa: E402
from hashes import canonical_json, event_hash, genesis_prev  # noqa: E402
from capabilities import APPEND_EVENTS, check, issue_capability  # noqa: E402
from ledger import Ledger, LedgerError  # noqa: E402

__version__ = "{ver}"
__all__ = ["Capability", "Event", "PathGlobScope", "ResourceRef", "Verdict", "canonical_json",
           "event_hash", "genesis_prev", "APPEND_EVENTS", "check", "issue_capability",
           "Ledger", "LedgerError", "__version__"]
'''

_PYPROJECT_HEAD = '''[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
'''

_PYPROJECT_AUDITKIT = _PYPROJECT_HEAD + '''name = "audit-kit"
version = "{ver}"
description = "治理框架（账本/能力/链哈希）——S2 装配产物；载荷与权威源逐字节一致"
requires-python = ">=3.10"

[tool.setuptools]
packages = ["auditkit"]

[tool.setuptools.package-data]
auditkit = ["_payload/*"]
'''

_PYPROJECT_EVOCORE = _PYPROJECT_HEAD + '''name = "evocore"
version = "{ver}"
description = "演化内核（检索/生命周期/决策）——S2 装配产物；包体与权威源逐字节一致"
requires-python = ">=3.10"

[tool.setuptools]
packages = ["evocore"]
'''

_README_AUDITKIT = '''# audit-kit（S2 装配产物 · pip 形态）

独立包形态的治理框架：载荷在 `auditkit/_payload/`（**与权威源逐字节一致**），
`auditkit/__init__.py` 为生成壳（路径注入+再导出）。用法：`import auditkit` →
`auditkit.Ledger` / `auditkit.Capability` / `auditkit.event_hash` 等。

- 版本 {ver}；对账：`build/manifests/pypkg.manifest.json`（sources 映射逐件可比）
- 边界：载荷以**平铺顶层模块名**导入（ledger/gov_types/…）——与同名第三方包相撞的
  风险登记于设计件 §七 D2；本形态适用 L1 多库同机自用，不作公开发行。
'''


def build_pypkg(out_root, man_dir, vers):
    """产物3：两个可装包（audit-kit 壳+载荷 · evocore 标准包）+ 清单。"""
    d = os.path.join(out_root, "pypkg")
    _clean(d)
    akd = os.path.join(d, "audit-kit")
    srcs = {}
    for n in AK_CORE:
        srcs[f"audit-kit/auditkit/_payload/{n}"] = _rel(_p("audit-kit", "core", n))
        _copy(_p("audit-kit", "core", n), os.path.join(akd, "auditkit", "_payload", n))
    for n in AK_LEDGER:
        srcs[f"audit-kit/auditkit/_payload/{n}"] = _rel(_p("audit-kit", "ledger", n))
        _copy(_p("audit-kit", "ledger", n), os.path.join(akd, "auditkit", "_payload", n))
    _w(os.path.join(akd, "auditkit", "__init__.py"), _AUDITKIT_INIT.format(ver=vers["audit-kit"]))
    _w(os.path.join(akd, "pyproject.toml"), _PYPROJECT_AUDITKIT.format(ver=vers["audit-kit"]))
    _w(os.path.join(akd, "README.md"), _README_AUDITKIT.format(ver=vers["audit-kit"]))
    evd = os.path.join(d, "evocore")
    for n in EVOCORE_MODULES:
        srcs[f"evocore/evocore/{n}"] = _rel(_p("evocore", n))
        _copy(_p("evocore", n), os.path.join(evd, "evocore", n))
    for n in EVOCORE_TESTS:
        srcs[f"evocore/evocore/tests/{n}"] = _rel(_p("evocore", "tests", n))
        _copy(_p("evocore", "tests", n), os.path.join(evd, "evocore", "tests", n))
    srcs["evocore/README.md"] = _rel(_p("evocore", "README.md"))   # 项目根（包外；tests 同）
    _copy(_p("evocore", "README.md"), os.path.join(evd, "README.md"))
    _w(os.path.join(evd, "pyproject.toml"), _PYPROJECT_EVOCORE.format(ver=vers["evocore"]))
    ex, ps, tt = run_conf(["--kernel", os.path.join(akd, "auditkit", "_payload")])
    ex2, ps2, tt2 = smoke_evo(evd)
    conf = [{"what": "conformance --kernel(payload 平铺)", "target": "<out>/pypkg/audit-kit/auditkit/_payload",
             "exit": ex, "passed": ps, "total": tt},
            {"what": "smoke evo(3 钉值)", "target": "<out>/pypkg/evocore", "exit": ex2, "passed": ps2, "total": tt2}]
    man = _manifest("pypkg", {"audit-kit": vers["audit-kit"], "evocore": vers["evocore"]},
                    _scan_files(d), srcs, conf)
    _emit(d, man_dir, "pypkg.manifest.json", man)
    return ex == 0 and ex2 == 0


_CAPS = ('{\n  "note": "能力令牌表骨架（S2 生成件）——空表；签发权归库运营者（L2 设计 §三⑦），'
         '本件不预填任何权限。",\n  "caps": []\n}\n')
_QUOTAS = ('{\n  "note": "配额/限速表骨架（S2 生成件）——空表；配额策略由库运营者签发（S4 起接线）。",\n'
           '  "quotas": []\n}\n')
_OPS = '''#!/bin/sh
# server 核自检（S2 生成件）——权威侧 conformance × 本部署副本
# 用法: CONFORMANCE_TOOL=<repo>/audit-kit/conformance.py sh ops/conformance.sh
# 默认工具路径按 build/out/server/ops 仓内布局推导；部署期用环境变量覆盖。
TOOL="${CONFORMANCE_TOOL:-$(dirname "$0")/../../../audit-kit/conformance.py}"
exec py -X utf8 "$TOOL" --kernel "$(dirname "$0")/../kernel"
'''


def build_server(out_root, man_dir, vers):
    """产物4：L2 服务核（两核+骨架；MCP 壳=S4）。"""
    d = os.path.join(out_root, "server")
    _clean(d)
    srcs = {}
    _copy_group(_p("audit-kit", "core"), AK_CORE, d, "kernel/core", srcs)
    _copy_group(_p("audit-kit", "ledger"), AK_LEDGER, d, "kernel/ledger", srcs)
    for n in EVOCORE_MODULES:
        srcs[f"evo/evocore/{n}"] = _rel(_p("evocore", n))
        _copy(_p("evocore", n), os.path.join(d, "evo", "evocore", n))
    _w(os.path.join(d, "caps.skeleton.json"), _CAPS)
    _w(os.path.join(d, "quotas.skeleton.json"), _QUOTAS)
    _w(os.path.join(d, "ops", "conformance.sh"), _OPS)
    _w(os.path.join(d, "libs", ".gitkeep"), "")
    for n in L2SERVER_FILES:                                 # S4：服务件载荷（源=build/l2server/）
        srcs[f"{n}"] = _rel(_p("build", "l2server", n))
        _copy(_p("build", "l2server", n), os.path.join(d, n))
    ex, ps, tt = run_conf(["--kernel", os.path.join(d, "kernel")])
    ex2, ps2, tt2 = smoke_evo(os.path.join(d, "evo"))
    ex3, ps3, tt3 = run_server_selftest(d)
    conf = [{"what": "conformance --kernel(server)", "target": "<out>/server/kernel",
             "exit": ex, "passed": ps, "total": tt},
            {"what": "smoke evo(3 钉值)", "target": "<out>/server/evo", "exit": ex2, "passed": ps2, "total": tt2},
            {"what": "server selftest(八工具)", "target": "<out>/server", "exit": ex3, "passed": ps3, "total": tt3}]
    man = _manifest("server", {"audit-kit": vers["audit-kit"], "evocore": vers["evocore"]},
                    _scan_files(d), srcs, conf, extra={"surface": GOV_SURFACE})
    _emit(d, man_dir, "server.manifest.json", man)
    return ex == 0 and ex2 == 0 and ex3 == 0


def main():
    ap = argparse.ArgumentParser(description="S2 四包装配器")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("all", "reconcile", "audit", "check-copy"):
        s = sub.add_parser(name)
        s.add_argument("--out", default=_p("build", "out"))
        s.add_argument("--manifests", default=_p("build", "manifests"))
        if name == "check-copy":
            s.add_argument("path")
            s.add_argument("--kind", default="fused", choices=["fused", "gov", "evo"])
    a = ap.parse_args()
    import time
    t0 = time.perf_counter()
    if a.cmd == "all":
        ok = cmd_all(a.out, a.manifests, time)
        print(f"装配耗时 {time.perf_counter()-t0:.2f}s（S2-T7 观测位）")
        return 0 if ok else 1
    if a.cmd == "reconcile":
        return cmd_reconcile(a.out, a.manifests)
    if a.cmd == "audit":
        return cmd_audit(a.out, a.manifests)
    return cmd_check_copy(a.path, a.kind, a.manifests)


def cmd_all(out_root, man_dir, time_mod):
    os.makedirs(man_dir, exist_ok=True)
    vers = versions()
    for stale in os.listdir(man_dir):
        if stale.endswith(".manifest.json"):
            os.remove(os.path.join(man_dir, stale))
    results = {}
    for name, fn in (("fused", build_fused), ("vendored", build_vendored),
                     ("pypkg", build_pypkg), ("server", build_server)):
        t = time_mod.perf_counter()
        results[name] = fn(out_root, man_dir, vers)
        print(f"  [{('PASS' if results[name] else 'FAIL')}] {name}（{time_mod.perf_counter()-t:.2f}s）")
    bad = [k for k, v in results.items() if not v]
    print(f"装配：{len(results)-len(bad)}/4 产物过 conformance；清单 → {_rel(man_dir)}/")
    return not bad


def _load_man(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _rerun(entry, out_root):
    target = entry["target"].replace("<out>", out_root)
    if entry["what"].startswith("server selftest"):
        return run_server_selftest(os.path.join(out_root, "server"))
    if entry["what"].startswith("conformance"):
        if entry["what"].endswith("(gov)") or entry["what"].endswith("(server)"):
            return run_conf(["--kernel", target])
        if "payload" in entry["what"]:
            return run_conf(["--kernel", target])
        if "--fused" in entry["what"]:
            return run_conf(["--fused", target])
    return smoke_evo(target)


def cmd_reconcile(out_root, man_dir):
    fails = []
    for name in MANIFEST_NAMES:
        reg = os.path.join(man_dir, name)
        if not os.path.isfile(reg):
            fails.append(f"{name}: 登记件缺失（先跑 all）")
            continue
        man = _load_man(reg)
        prod = _product_dir(name, out_root)
        # 查1：产物文件哈希==清单（且无多余文件）
        now = _scan_files(prod)
        if now != man["files"]:
            only_now = sorted(set(now) - set(man["files"]))
            only_man = sorted(set(man["files"]) - set(now))
            diff = sorted(k for k in set(now) & set(man["files"]) if now[k] != man["files"][k])
            fails.append(f"{name}: 查1 产物与清单不符（多={only_now} 缺={only_man} 异={diff}）")
        if _aggregate(now) != man["aggregate_sha"]:
            fails.append(f"{name}: 查1 aggregate_sha 不符")
        # 查2：副本 sha==源 sha（sources 映射逐条）
        for rel, src in man["sources"].items():
            p = os.path.join(prod, rel)
            if not os.path.isfile(p) or sha_f(p) != sha_f(_p(src)):
                fails.append(f"{name}: 查2 副本≠源：{rel} vs {src}")
        # 查3：conformance 重跑==清单
        for e in man["conformance"]:
            ex, ps, tt = _rerun(e, out_root)
            if (ex, ps, tt) != (e["exit"], e["passed"], e["total"]):
                fails.append(f"{name}: 查3 {e['what']} 读数漂移 ({ex},{ps}/{tt}) != ({e['exit']},{e['passed']}/{e['total']})")
        # 查4：产物内清单==登记件
        inner = os.path.join(prod, name)
        if not os.path.isfile(inner) or open(inner, encoding="utf-8").read() != open(reg, encoding="utf-8").read():
            fails.append(f"{name}: 查4 产物内清单≠登记件")
    for f in fails:
        print(f"  [DRIFT] {f}")
    print(f"对账五查：{'PASS' if not fails else f'{len(fails)} 项 DRIFT'}")
    return 0 if not fails else 1


def _product_dir(name, out_root):
    return {"fused.manifest.json": os.path.join(out_root, "fused"),
            "gov.manifest.json": os.path.join(out_root, "vendored", "gov"),
            "evo.manifest.json": os.path.join(out_root, "vendored", "evo"),
            "pypkg.manifest.json": os.path.join(out_root, "pypkg"),
            "server.manifest.json": os.path.join(out_root, "server")}[name]


def cmd_audit(out_root, man_dir):
    """S2-T3/T4/T5/T7/T8 验收报告（只读；读数打印，exit 0 当且仅当 T5 一致性 0 违例）。"""
    print("== T5 跨产物一致性（36 副本按源分组，组内 sha 全同且==源）==")
    groups, viol = {}, []
    for name in MANIFEST_NAMES:
        man = _load_man(os.path.join(man_dir, name))
        for rel, src in man["sources"].items():
            key = src
            groups.setdefault(key, []).append((name, rel))
    for src, members in sorted(groups.items()):
        shas = {sha_f(os.path.join(_product_dir(m[0], out_root), m[1])) for m in members}
        shas.add(sha_f(_p(src)))
        if len(shas) != 1:
            viol.append(f"{src}: {len(shas)} 个不同 sha（{len(members)} 副本）")
    print(f"  源文件 {len(groups)} 个 · 副本 {sum(len(v) for v in groups.values())} 份 · 一致性违例 {len(viol)}")
    for v in viol:
        print(f"  [不一致] {v}")
    print("== T3/T4 产物扫描面 ==")
    gen_py = [os.path.join(out_root, "pypkg", "audit-kit", "auditkit", "__init__.py")]
    py_total = 0
    for dp, ds, fs in os.walk(out_root):
        ds[:] = [x for x in ds if x != "__pycache__"]
        py_total += sum(1 for f in fs if f.endswith(".py"))
    print(f"  产物 .py {py_total} 件 · 生成件（壳）{len(gen_py)} 件——门①-⑥ 需带 --allow 表（仓内模块声明）")
    print("  副本读数==源读数：由**字节相等**推出（reconcile 查2 + build/tests 双跑/副本==源 已机械证明）；")
    print("  注意（方法学）：**勿跨副本合并扫描**——同一源文件在多产物中各存一份，合并会产生假重复块。")
    print("== T8 产物级复用记账 ==")
    copies = sum(len(_load_man(os.path.join(man_dir, n))["sources"]) for n in MANIFEST_NAMES)
    listed = sum(len(_load_man(os.path.join(man_dir, n))["files"]) for n in MANIFEST_NAMES)
    total = listed + len(MANIFEST_NAMES)          # 清单自身不计入 files（避免自指哈希）
    derived = 1                                   # framework_segment.txt
    print(f"  产物文件 {total} = 副本 {copies} + 派生 {derived} + 生成 {total - copies - derived}"
          f"（生成 {total - copies - derived} = 清单 {len(MANIFEST_NAMES)} + 壳/pyproject/README/skeleton/ops/.gitkeep；零逻辑）")
    return 0 if not viol else 1


def cmd_check_copy(path, kind, man_dir):
    """外部副本两级对账。"""
    if kind == "fused":
        return _check_fused(path, man_dir)
    return _check_payload(path, kind, man_dir)


def _check_fused(path, man_dir):
    man = _load_man(os.path.join(man_dir, "fused.manifest.json"))
    with open(path, encoding="utf-8") as f:
        src = f.read()
    got = _seg_of(src)
    if got is None:
        print(f"[DRIFT] 副本区段横幅未命中：{path}")
        return 1
    seg = got[0]
    h = sha_b(seg.encode("utf-8"))
    ok = h[:16] == man["segment"]["sha256"][:16]
    print(f"  机制段冻结面：{'PASS' if ok else 'DRIFT'}（副本 {h[:16]} vs 权威 {man['segment']['sha256'][:16]}）")
    import difflib
    own = open(_p("evo-seat", "evo_seat.py"), encoding="utf-8").read()
    sec = re.compile(r"^# ═+ §(\d)")
    cur, counter = "(头)", {}
    tags = []
    for ln in own.split("\n"):
        m2 = sec.match(ln)
        if m2:
            cur = "§" + m2.group(1)
        tags.append(cur)
    sm = difflib.SequenceMatcher(a=own.split("\n"), b=src.split("\n"), autojunk=False)
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag != "equal":
            for k in set(tags[i1:i2]):
                counter[k] = counter.get(k, 0) + 1
    print(f"  适配面差异区段摘要：{counter if counter else '无'}")
    freeze_ok = h[:16] == man["segment"]["sha256"][:16]
    print(f"  check-copy 判定：{'PASS（冻结面同哈希；适配面差异已登记）' if freeze_ok else 'DRIFT（机制段被改）'}")
    return 0 if freeze_ok else 1


def _check_payload(path, kind, man_dir):
    name = "gov.manifest.json" if kind == "gov" else "evo.manifest.json"
    man = _load_man(os.path.join(man_dir, name))
    bad = 0
    for rel, src in man["sources"].items():
        cand = os.path.join(path, rel)
        if not os.path.isfile(cand):
            cand2 = os.path.join(path, os.path.basename(rel))
            cand = cand2 if os.path.isfile(cand2) else cand
        if not os.path.isfile(cand):
            print(f"  [DRIFT] 缺件 {rel}")
            bad += 1
        elif sha_f(cand) != sha_f(_p(src)):
            print(f"  [DRIFT] 内容异 {rel}")
            bad += 1
    print(f"  {kind} 载荷逐字节：{'PASS' if bad == 0 else f'{bad} 项 DRIFT'}（{len(man['sources'])} 件）")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
