# -*- coding: utf-8 -*-
"""prereg.py — audit-kit L0：判据件（预注册）机械格式 + 引用指针（S8-5 · 20260923 开工批）

病灶：SPEC §B-3「判据注入」是宿主三件事之三，但此前体检**只检目录存在**
（`conformance` 的「prereg 判据位非空」= `len(os.listdir(dir)) >= 1`）——判据件写了什么、
有没有版本、能不能被决策留痕引用，全无人管。于是「有判据」与「有个空目录/一份没版本的草稿」
在体检输出上**同形**（第一定理）。本件把判据件的**可引用性**变成机械判据。

必检两项（缺一即 FAIL，负向对照见 `build/tests/test_prereg_gate.py`）；
只在**件首 20 行**（元数据区）内找——判据件常自带写法示例，不设边界会让示例文字蒙过检查：
  版本行    `版本：v1` / `版本: v1` / `version: v1`
  生效日行  `生效：2026-09-21` / `生效日期：2026-09-21`（ISO 8601）

引用锚：默认**机械派生** `<相对名>@<版本>`；判据件若自带 `判据锚：<id>` 行则以它为准
（自带锚的好处=文件改名/移动时引用不断）。默认走派生而不是强制自带，是为了让**既有判据件
不必为了过体检而被改写**——判据件自身的纪律是「修改走新版本文件，不改本件」。

留痕用法（S8-5②）：决策留痕结构增 `prereg` 字段——有判据件则带 `文件@版本`，无则 `null`。
「判据先于实现」由此落到**每条决策**上：读账就能看出这条判定当时有没有判据可依。

零依赖（只用 stdlib）；不碰账本、不碰演化核——本件属治理核的判据面。
"""
from __future__ import annotations

import os
import re

NL = chr(10)                   # 换行符常量（避免源码内转义字面量在写入管道里被展开）

# 版本行：允许 markdown 引用符/粗体星号前缀；值取到空白或中文句读为止
_RE_VERSION = re.compile(r"版本\s*[:：]\s*([^\s。，,;；）)]+)")
_RE_VERSION_EN = re.compile(r"\bversion\s*[:：]\s*([^\s。，,;；）)]+)", re.IGNORECASE)
# 生效日行：`生效：` / `生效日期：` / `effective:`，值必须是 ISO 8601 日期
_RE_EFFECTIVE = re.compile(r"(?:生效日期|生效|effective)\s*[:：]\s*(\d{4}-\d{2}-\d{2})")
# 自带引用锚（可选）
_RE_ANCHOR = re.compile(r"判据锚\s*[:：]\s*([^\s。，,;；）)]+)")

REQUIRED = (("版本行", (_RE_VERSION, _RE_VERSION_EN)), ("生效日行", (_RE_EFFECTIVE,)))
SKIP_NAMES = ("README.md",)          # 目录说明不是判据件（模板骨架靠它非空，但不该被当判据）
# 元数据区：只在件首 N 行内找必检项。
# 为什么必须限制——判据件常常**自带写法说明**（"必带 `版本：vN`"这类示例文字），
# 不设边界时示例会被当成合格元数据，于是"删掉版本行"照样过检（检查自败）。
# 实测踩过：起步判据件 §三 的示例文字命中正则，负向对照假通过。
HEAD_LINES = 20


def _head(text: str) -> str:
    """取件首元数据区（见 `HEAD_LINES` 的自败教训）。"""
    return NL.join(text.splitlines()[:HEAD_LINES])


def parse(text: str) -> dict:
    """从判据件**元数据区**抽出 {version, effective, anchor}；缺项为 None。"""
    text = _head(text)
    ver = None
    for rx in (_RE_VERSION, _RE_VERSION_EN):
        m = rx.search(text)
        if m:
            ver = m.group(1)
            break
    eff = _RE_EFFECTIVE.search(text)
    anc = _RE_ANCHOR.search(text)
    return {"version": ver, "effective": eff.group(1) if eff else None,
            "anchor": anc.group(1) if anc else None}


def missing_markers(text: str) -> list:
    """返回缺失的必检项名（空列表=格式合格）。只看元数据区。"""
    head = _head(text)
    out = []
    for name, rxs in REQUIRED:
        if not any(rx.search(head) for rx in rxs):
            out.append(name)
    return out


def scan_dir(dirpath: str, skip=SKIP_NAMES) -> tuple:
    """扫判据目录 → `(refs, problems)`。

    refs     = [(相对名, 派生锚)]，只含格式合格者；按名排序（确定性）。
    problems = [(相对名, [缺失项])]，格式不合格者（含读不出的件，原因写进缺失项）。
    """
    refs, problems = [], []
    if not os.path.isdir(dirpath):
        return refs, problems
    for name in sorted(os.listdir(dirpath)):
        if name in skip or not name.endswith(".md"):
            continue
        full = os.path.join(dirpath, name)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            problems.append((name, [f"不可读（{type(e).__name__}）"]))
            continue
        miss = missing_markers(text)
        if miss:
            problems.append((name, miss))
            continue
        info = parse(text)
        refs.append((name, info["anchor"] or f"{name}@{info['version']}"))
    return refs, problems


def find_ref(dirpath: str) -> str:
    """给决策留痕用的判据指针：合格判据件的锚。

    0 份合格 → `None`（留痕写 null，读账即知"这条判定当时无判据可依"）；
    1 份 → 该份的锚；多份 → **字典序首份**（确定性；一库一判据件为常态，
    多份时其余须在判据件内互相引用，或由调用方自行选择并显式传值）。
    """
    refs, _problems = scan_dir(dirpath)
    return refs[0][1] if refs else None
