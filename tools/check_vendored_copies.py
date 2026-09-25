# -*- coding: utf-8 -*-
"""check_vendored_copies.py — 副本族逐字节一致性校验（重影防线 · 20260925 重构第一轮）

背景（MAP.md 实测）：本仓发布面存在多份"应同字节"的副本；它们分属自足分发单元，
不能合并为单一真源（合并=改包结构），但**漂移必须被机械发现**——本器即这道闸。

族表 FAMILIES 为声明式清单：新族随勘验随时挂入，族内允许 1..N 件，逐字节 sha256 对齐。
已知分叉（**不是**本器管辖的族，勿混入）：invariant_scanner.py 的 tools/ 现役版
（58cf50c7…，含 W2-N7b 修复）与 skill/sekb 发布面成对版（20709e06…）是**两个谱系**，
是否同步属治理位裁决，本器只锁"发布面成对版互不漂移"。

用法：py -X utf8 tools/check_vendored_copies.py   （零参数；路径一律仓根自定位）
退出码：0=全族齐；1=有族漂移或缺件；2=族表空（配置错误）。
"""
import hashlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

FAMILIES = {
    "migrate.py ×4（skill 安装面）": [
        "tools/skill-installer/migrate.py",
        "skill/migrate.py",
        "sekb-dsh-package/migrate.py",
        "sekb-plugin/skills/self-evolving-kb/migrate.py",
    ],
    "invariant_scanner.py 发布面成对版（旧谱系，与 tools/ 现役版分叉系已知）": [
        "skill/invariant_scanner.py",
        "sekb-plugin/skills/self-evolving-kb/invariant_scanner.py",
    ],
}


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    if not FAMILIES:
        print("族表为空——配置错误")
        return 2
    bad = 0
    for name, rels in FAMILIES.items():
        hashes = {}
        missing = []
        for rel in rels:
            p = os.path.join(_ROOT, rel)
            if not os.path.isfile(p):
                missing.append(rel)
            else:
                hashes[rel] = _sha256(p)
        if missing:
            print(f"[FAIL] {name}：缺件 {missing}")
            bad += 1
            continue
        distinct = sorted(set(hashes.values()))
        if len(distinct) == 1:
            print(f"[PASS] {name}：{len(hashes)} 件同字节（{distinct[0][:16]}…）")
        else:
            print(f"[FAIL] {name}：{len(distinct)} 种字节并存——")
            for rel, h in hashes.items():
                print(f"        {h[:16]}…  {rel}")
            bad += 1
    print(f"副本族：{len(FAMILIES) - bad}/{len(FAMILIES)} 齐")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
