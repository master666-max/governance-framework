#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_release.py — S7 发布件打包器（依《S7预注册-交付评审》R-4 · 判据冻结）

产物：`dist/发布-sys-v1.0/`（staging 目录）+ `dist/发布-sys-v1.0.zip`（发布件）
判据落实：
  ① **双跑逐位相同**：zip 固定时间戳（2000-01-01 00:00:00）、条目排序、固定压缩级别；
  ② **SELF.sha256 自校验**：覆盖 bundle 内全部文件（相对路径排序），`--verify` 解包复核；
  ③ **解包冒烟**：`--smoke <解包目录>` 在解包位跑装配链+融合件+服务件（见变更请求表 S7-CR1）。
脱敏面（E2）：不含内部治理记录（日志/账本/交接件/交付台记录/工具）；排除 __pycache__ 与 build/out。

用法:
  py -X utf8 build/make_release.py build [--dist dist]
  py -X utf8 build/make_release.py --verify dist/发布-sys-v1.0.zip
  py -X utf8 build/make_release.py --smoke <解包目录>
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = "发布-sys-v1.0"
DOCS = {"说明书-三形态-20260923.md": "说明书-三形态.md",
        "指南-迁移与装配切换-20260923.md": "指南-迁移与装配切换.md",
        "索引与术语-20260923.md": "索引与术语.md"}
DOC_SRC = os.path.join(ROOT, "交付-S1v2-20260923")
SRC_DIRS = ("audit-kit", "evocore", "evo-seat", "memsys", "build")
EXCLUDE_DIRS = {"__pycache__", "out", "manifests", "state"}
EXCLUDE_FILES = {".pyc", ".pyo"}
ZIP_STAMP = (2000, 1, 1, 0, 0, 0)
_Z = zipfile.ZIP_DEFLATED

BOUNDARIES = [
    ("真实 pip 安装未实测", "只验证了「从装配目录直接导入」", "需要真装验证时"),
    ("服务件 HTTP 传输为骨架级（POST 绑定）", "要求流式的客户端暂不满足", "遇到流式客户端"),
    ("能力令牌只到运营者级", "细粒度签发/配额执行未上", "多人多源共用时"),
    ("目录扫描限定在库目录内", "有意为之（防越权读取）", "需要扫库外时显式放宽并留痕"),
    ("坏时间戳两形态行为不同（报错停下 / 按零龄继续）", "已登记，未统一", "需要两形态严格一致时"),
    ("中库「就地换治理件」没有一键工具", "用「重建目录+拷回库文件」替代", "换件成为高频操作时"),
    ("中库 index/ 自动生成器未提供", "内容随用随长", "首个真实宿主接入时"),
    ("融合单文件有若干未命名常量", "不影响行为", "内核版本周期"),
    ("发布件不含内部治理记录", "面向对外读者（脱敏面）", "治理位要求调整发布面时"),
    ("无远端（push 不适用）", "环境事实", "加远端时"),
]


def _version_table():
    """R-6：组件版本表（声明处读取 + 声明件 sha16）。"""
    def sha16(p):
        with open(os.path.join(ROOT, p), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]

    def grab(p, rgx):
        with open(os.path.join(ROOT, p), encoding="utf-8") as f:
            m = re.search(rgx, f.read(), re.M)
        if not m:
            raise SystemExit(f"版本声明未命中：{p}")
        return m.group(1)
    return [
        ("audit-kit", open(os.path.join(ROOT, "audit-kit", "VERSION"), encoding="utf-8").read().strip(),
         "audit-kit/VERSION"),
        ("evocore", grab("evocore/__init__.py", r'^__version__ = "([^"]+)"'), "evocore/__init__.py"),
        ("evo-seat", grab("evo-seat/evo_seat.py", r'^VERSION = "([^"]+)"'), "evo-seat/evo_seat.py"),
        ("L2 服务件", grab("build/l2server/server.py", r'SERVER_VERSION = "([^"]+)"'),
         "build/l2server/server.py"),
        ("中库规范", grab("build/make_kb.py", r'"kb_spec_version": "([^"]+)"'), "build/make_kb.py"),
    ]


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _copy_tree(src, dst):
    for dp, ds, fs in os.walk(src):
        ds[:] = [d for d in ds if d not in EXCLUDE_DIRS]
        rel = os.path.relpath(dp, src)
        for f in sorted(fs):
            if os.path.splitext(f)[1] in EXCLUDE_FILES:
                continue
            d = os.path.join(dst, rel, f) if rel != "." else os.path.join(dst, f)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(os.path.join(dp, f), d)


def _bundle_files(stage):
    out = []
    for dp, ds, fs in os.walk(stage):
        ds[:] = [d for d in ds if d != "__pycache__"]
        for f in sorted(fs):
            full = os.path.join(dp, f)
            out.append(os.path.relpath(full, stage).replace("\\", "/"))
    return sorted(out)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _build_readme(vt):
    rows = "\n".join(f"| {n} | {v} | `{p}` |" for n, v, p in vt)
    bd = "\n".join(f"| {i+1} | {a} | {b} | {c} |" for i, (a, b, c) in enumerate(BOUNDARIES))
    return f"""# 发布说明 · sys-v1.0（体系 v1.0）

> 这是一套"知识库三形态"的完整发布件：同一套底层（账本语义/检索/衰减），三种装配
> （单文件/包内目录/服务进程）。读者面三份文档在 `docs/`；代码面在对应目录。

## 一 · 版本

体系版本 **sys-v1.0**（=本次交付评审的宣告版本；**体系版本 ≠ 组件版本**，两者并列不混称）：

| 组件 | 版本 | 声明处 |
|---|---|---|
{rows}

## 二 · 怎么验收（复跑清单）

```bash
py -X utf8 build/assemble.py all                      # 四产物装配（含各产物自带合规检查）
py -X utf8 build/assemble.py reconcile                # 对账五查
py -X utf8 build/out/fused/evo_seat.py selftest       # 融合形态自检
py -X utf8 build/out/server/server.py selftest        # 服务件自检（八工具）
py -X utf8 audit-kit/conformance.py --fused build/out/fused/evo_seat.py
py -X utf8 audit-kit/conformance.py --kernel audit-kit
py -X utf8 build/demo_e2e.py                          # 三形态端到端 + 跨形态一致性对照
```

期望读数见 `docs/说明书-三形态.md` 附录表与 `docs/指南-迁移与装配切换.md` 附录表
（豁免口径：仅耗时/时间戳/临时路径/ResourceWarning 行可漂移，其余逐字相等）。

## 三 · 已知边界（发布版 · 如实列出）

| # | 事项 | 现状 | 何时处理 |
|---|---|---|---|
{bd}

---
*审计区 · sys-v1.0 发布件 · 打包器 `build/make_release.py`（确定性：固定时间戳/排序/固定压缩级）*
"""


def build(dist):
    stage = os.path.join(dist, BUNDLE)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    # VERSION + README
    vt = _version_table()
    lines = ["体系版本: sys-v1.0", "组件版本:"]
    for n, v, p in vt:
        lines.append(f"  {n} {v}  ({p} sha256[:16]={_sha(os.path.join(ROOT, p))[:16]})")
    lines.append("评审记录: 交付-S1v2-20260923/S7-验收报告.md（仓内路径；本 bundle 不含内部记录）")
    _w(os.path.join(stage, "VERSION"), "\n".join(lines) + "\n")
    _w(os.path.join(stage, "README-发布说明.md"), _build_readme(vt))
    # docs（改名去日期：对外读者面）
    os.makedirs(os.path.join(stage, "docs"), exist_ok=True)
    for src, dst in DOCS.items():
        shutil.copyfile(os.path.join(DOC_SRC, src), os.path.join(stage, "docs", dst))
    # 代码面
    for d in SRC_DIRS:
        _copy_tree(os.path.join(ROOT, d), os.path.join(stage, d))
    _copy_tree(os.path.join(ROOT, "build", "manifests"), os.path.join(stage, "manifests"))
    # SELF.sha256
    rows = [f"{h}  {rel}" for rel in _bundle_files(stage)
            for h in [_sha(os.path.join(stage, rel))]]
    _w(os.path.join(stage, "SELF.sha256"), "\n".join(rows) + "\n")
    # zip（确定性）
    zpath = os.path.join(dist, BUNDLE + ".zip")
    if os.path.isfile(zpath):
        os.remove(zpath)
    files = _bundle_files(stage)
    with zipfile.ZipFile(zpath, "w", _Z, compresslevel=9) as z:
        for rel in files:
            zi = zipfile.ZipInfo(f"{BUNDLE}/{rel}", date_time=ZIP_STAMP)
            zi.compress_type = _Z
            zi.external_attr = 0o644 << 16
            with open(os.path.join(stage, rel), "rb") as f:
                z.writestr(zi, f.read())
    print(f"build: {os.path.relpath(zpath, ROOT)}（{len(files)} 文件 · "
          f"{os.path.getsize(zpath)} 字节 · zip sha256={_sha(zpath)[:16]}）")
    return 0


def verify(zpath):
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zpath) as z:
            z.extractall(td)
        stage = os.path.join(td, BUNDLE)
        self_path = os.path.join(stage, "SELF.sha256")
        rows = {}
        with open(self_path, encoding="utf-8") as f:
            for line in f:
                h, _, rel = line.strip().partition("  ")
                rows[rel] = h
        live = _bundle_files(stage)
        live = [r for r in live if r != "SELF.sha256"]
        bad = []
        if sorted(rows) != live:
            bad.append(f"清单与实际不符：缺 {sorted(set(rows) - set(live))} 多 {sorted(set(live) - set(rows))}")
        for rel in live:
            if rows.get(rel) != _sha(os.path.join(stage, rel)):
                bad.append(f"哈希不符：{rel}")
        print(f"verify: {'PASS' if not bad else 'FAIL'}（{len(live)} 文件）")
        for b in bad:
            print("  " + b)
        return 0 if not bad else 1


def smoke(where):
    """解包冒烟（S7-CR1：装配链 + 融合件 + 服务件，全部在解包位自足执行）。
    绝对化 `where`：相对路径与 cwd=where 叠加会把路径解析两遍（实测抓到的坑）。"""
    where = os.path.abspath(where)
    steps = [
        (["build/assemble.py", "all"], "装配：4/4 产物过 conformance"),
        ([None], "SMOKE 融合：init/append/verify"),
        (["build/out/server/server.py", "selftest"], "selftest: 9/9"),
    ]
    rc_all = 0
    for argv, expect in steps:
        if argv[0] is None:                        # 融合件冒烟（临时库）
            lib = os.path.join(where, "build", "out", "smoke", "kb.db")
            seat = os.path.join(where, "build", "out", "fused", "evo_seat.py")
            cmds = [[seat, "init", lib, "--level", "G1"],
                    [seat, "append", lib, "--id", "s1", "--content", "冒烟样本 玻璃", "--keywords", "玻璃"],
                    [seat, "verify", lib]]
            outs = []
            for c in cmds:
                r = subprocess.run([sys.executable, "-X", "utf8", *c], cwd=where,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8")
                outs.append(r.stdout)
                rc_all |= r.returncode
            ok = rc_all == 0 and "链完整" in outs[-1]
            print(f"smoke: {'PASS' if ok else 'FAIL'} {expect}")
            continue
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(where, argv[0]), *argv[1:]],
                           cwd=where, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8")
        ok = r.returncode == 0 and expect in r.stdout
        rc_all |= 0 if ok else 1
        print(f"smoke: {'PASS' if ok else 'FAIL'} {argv[0]} {expect}")
        if not ok:
            print(r.stdout[-400:])
    print(f"smoke: {'PASS' if rc_all == 0 else 'FAIL'}")
    return rc_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="build", choices=["build"])
    ap.add_argument("--dist", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--verify", default=None)
    ap.add_argument("--smoke", default=None)
    a = ap.parse_args()
    if a.verify:
        return verify(a.verify)
    if a.smoke:
        return smoke(a.smoke)
    return build(a.dist)


if __name__ == "__main__":
    sys.exit(main())
