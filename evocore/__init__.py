# -*- coding: utf-8 -*-
"""evocore — 演化内核独立包（S1：自 memsys/engine 平移 · 一码四包的"码"源）

公开面 = SPEC §C Kernel Interface 中本包承担的部分（检索/生命周期/决策的纯函数）。
LedgerLike/ScannerLike 不在本包（归 audit-kit）——evocore 零依赖，不碰账本。

导出名注记：S1 设计件 §5 写的是概括名 `tokens`/`adjudicate`；实现实名为
`_tokens`（私有，按 S1"不改名"纪律不导出）与 `adjudicate_{conflict,merge,promote}`
（三 intent 各一函数）。本包按**实名**导出。
"""
__version__ = "0.5.0"
# 版本记录（S1v2 · 2026-09-23 · 总工单对齐轮 · 设计件《S1设计v2-evocore全量落地架构》）：
#   0.1.0  S1 平移版（自 memsys/engine，零语义变更）
#   0.1.1  S1v2 加固轮：T1 衰减映射单一化（tunables.decay_mult）· T2 常量命名化
#          （rationale_max/_SECONDS_PER_DAY）· T3 bad-ts 语义钉桩 · 契约测试与坏味基线。
#          **行为逐位不变**——证据：py -X utf8 tools/S1_verify_behavior.py（33 用例差异 0）。
#   0.2.0  S3/T1 加法式增补：新模块 entry.py（TYPES + validate_entry，宿主写入口构造校验）——
#          **不改动现有五件一字**；行为对拍仍 33 用例差异 0。
#   0.3.0  S4/T1 加法式增补：新模块 project.py（事件流→条目集投影，**单一投影器**：
#          kb CLI 与 L2 server 共用；另补 tombstone 回放）；行为对拍仍 33 用例差异 0。
#   0.5.0  P3/D7 统一（20260924 第三方接收）：content_hash 全宽 64 hex + created_at 入排除集（evocore-D7 关闭）
#   0.4.0  S8-4 加法式增补（20260923 开工批）：project.py 增 `project_overrides` /
#          `override_marks`（人侧终裁事件投影，与融合件 §7 `_overrides`/`_override_marks` 同语义）；
#          同批 W2-N3 使 `project_entries` **两认形态词汇**（entry_append/memory_append 等）。
#          原六件一字未动；行为对拍仍 33 用例差异 0。
SPEC = "SPEC-内核接口与宿主契约-v1"

from .tunables import Tunables, DEFAULTS
from .retrieval import score, recall, retrieve
from .lifecycle import route, promote, attic, tombstone, touch, decay_multiplier
from .decision import adjudicate_conflict, adjudicate_merge, adjudicate_promote
from .entry import TYPES, content_hash, validate_entry
from .project import (project_entries, project_overrides, project_sources,
                     override_marks, OVERRIDE_KIND)
from . import tunables, retrieval, lifecycle, decision, entry, project

__all__ = [
    "__version__", "SPEC",
    # tunables
    "Tunables", "DEFAULTS",
    # retrieval
    "score", "recall", "retrieve",
    # lifecycle
    "route", "promote", "attic", "tombstone", "touch", "decay_multiplier",
    # decision
    "adjudicate_conflict", "adjudicate_merge", "adjudicate_promote",
    # entry（S3/T1）
    "TYPES", "validate_entry", "content_hash",
    # project（S4/T1；S8-4 增补终裁投影）
    "project_entries", "project_overrides", "project_sources",
    "override_marks", "OVERRIDE_KIND",
]
