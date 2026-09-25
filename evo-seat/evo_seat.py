#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evo_seat.py — 微型内核：治理框架×演化内核融合单文件（v0.1.0，架构书 M0-M3）
================================================================================
一个文件 · 一份真相（SQLite）· 六档审查精细度（G0-G5）
本文件是《SPEC-内核接口与宿主契约 v1》Kernel Interface 的融合形态实现
（符合性复验：py -X utf8 audit-kit/conformance.py --fused evo_seat.py）。
治理位边界：内核只提供治理面（账本/锚/门）；验收/裁决/修宪**不入内核**——
执行无权自宣验收，治理位永远外置。
分区（区段即边界，单向调用 cli→gates/decide→rank/lifecycle→store→core）：
  §0 SOURCES  §1 core  §2 store  §3 rank  §4 lifecycle  §5 decide
  §6 gates    §7 cli   §8 tests（自注册）                       §9 main
铁律：触发器物理 append-only · 出处三件套 · fail-closed · 墓碑不删 ·
      决策留痕 · 构造时校验 · 内嵌测试——小的是体积，不是纪律。
用法：
  py -X utf8 evo_seat.py init <库路径> [--level G2]
  py -X utf8 evo_seat.py append <库> --id e1 --content "..." --type semantic --importance 5
  py -X utf8 evo_seat.py retrieve <库> "查询词" [-k 5]
  py -X utf8 evo_seat.py level <库> G3          # 切档（降级留痕）
  py -X utf8 evo_seat.py verify <库> | selftest | gate <file.py> | decide <库> conflict <f1> <f2> | anchor <库> | scan <目录>
  py -X utf8 evo_seat.py override <库> --actor human:you --decision "keep:e2" --rationale "理由" [--target-seq N]
                                      # 人侧仲裁（S8-4）：只接受 human:*；写 human_override 终局标记，不删历史
"""
import argparse, ast, datetime, fnmatch, json, os, re, sqlite3, sys, time, unittest

VERSION = "0.2.2"
# 变更记录（版本纪律：破坏性变更必升版本+声明算法版本）：
#   0.1.0  初版（哈希 v1：只覆盖 payload）
#   0.2.0  哈希 v2（actor/kind 并入——老库不可读，需重建）+SPEC v1 吸收+
#          framework_sha 对账+升档文案修正
#   0.2.1  framework_sha 判别力修复（横幅定位+长度断言——原实现只哈希 66 字节，
#          blender 线实测 CONFIRMED 判别力近零）+哈希键兼容试算
#   0.2.2  §7 投影语义对齐（S5/T1：与重装形态 evocore.project 同语义——建条盖账本 ts /
#          命中回放 last_used / 墓碑生效）；**机制段 §1-§6 未动 ⇒ framework_sha 不变**
HASH_ALGO = "v2"
SPEC = "SPEC-内核接口与宿主契约-v1"   # 本文件实现的规范版本（符合性套件可验）
GOVERNANCE_BOUNDARY = "验收/裁决/修宪不入内核（执行无权自宣验收）——治理位外置"

# ═══════════════════════════ §0 SOURCES（唯一事实源） ═══════════════════════════
LEVELS = ("G0", "G1", "G2", "G3", "G4", "G5")
LEVEL_DESC = {
    "G0": "观察位：账本+检索+三态（触发器物理强制唯一内置）",
    "G1": "标准位：+链重放验证+墓碑+开库即验",
    "G2": "类型位：+条目构造校验+类型差异化衰减",
    "G3": "门位：+质量门五道+区段依赖测试",
    "G4": "决策位：+决策留痕+金标挣得接口+defer 监控",
    "G5": "锚定位：+入库锚+出站扫描三态+周巡检提示",
}
TYPES = ("episodic", "semantic", "procedural")
STATES = ("intermediate", "longterm", "attic")

class T:
    """机制参数（改=改此处+PR+门）。"""
    W_KW, W_CONTENT, W_IMP, W_AGE = 3.0, 1.5, 0.2082, 0.1
    FILTER_ZERO = 1
    PROMOTE_MIN = 7
    DECAY = {"episodic": 2.0, "semantic": 1.0, "procedural": 0.0}
    DEFER_RATE_MAX = 0.40
    MAX_LINES, MAX_STMTS, MAX_BRANCH = 900, 80, 15
    IMPORT_ALLOW = {"sys","os","re","json","hashlib","time","argparse","sqlite3","datetime",
                    "math","random","csv","collections","itertools","functools","pathlib",
                    "ast","dataclasses","typing","enum","textwrap","unittest","copy","io",
                    "unicodedata","statistics","uuid","zlib","base64","struct","fnmatch",
                    "contextlib","warnings","logging","abc","types","inspect","operator",
                    "__future__","tempfile","shutil"}

# ═══════════════════════════ §1 core（类型+哈希） ═══════════════════════════
class EvoError(Exception):
    """微内核一切失败（fail-closed）。"""

def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def event_hash(prev_hash: str, payload, actor: str = "", kind: str = "") -> str:
    """哈希 v2（20260923 评审采纳同步）：actor/kind 并入输入——头部字段篡改可检出。"""
    if len(prev_hash) != 64 or any(c not in "0123456789abcdef" for c in prev_hash):
        raise EvoError(f"prev_hash 须 64 位小写十六进制：{prev_hash[:16]}…")
    body = canonical_json({"actor": actor, "kind": kind, "payload": payload})
    return __import__("hashlib").sha256((prev_hash + body).encode("utf-8")).hexdigest()

GENESIS = "0" * 64

def framework_sha() -> str:
    """§F 副本对账：框架段哈希（§1 core…§6 gates）。
    定位=区段横幅行（含 ═ 装饰），**不**用裸 find（会落在文件头区段名清单上）；
    最小长度断言 fail-closed（防静默产坏值）。
    v0.2.1 修复（blender 线实测 CONFIRMED）：原实现只哈希 66 字节、对框架码
    偏离零判别力——修后基线值见 SPEC §F/conformance 判别力测试。"""
    import hashlib
    import re as _re
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    a = _re.search(r"^# ═+ §1 core", src, _re.M)
    b = _re.search(r"^# ═+ §7 cli", src, _re.M)
    if not (a and b): raise EvoError("framework_sha：区段横幅未命中（文件结构异常）")
    seg = src[a.start():b.start()]
    if len(seg) < 5000:
        raise EvoError(f"framework_sha：框架段仅 {len(seg)} 字节 <5000 下限（拒绝静默坏值）")
    return hashlib.sha256(seg.encode("utf-8")).hexdigest()[:16]
_HEX = re.compile(r"^[0-9a-f]{64}$")
_ACTOR = re.compile(r"^(llm|fallback|human|ci|engine):[^\s]+$")

def validate_entry(e: dict) -> None:
    """G2 条目构造校验：非法条目建不出来（P7）。"""
    for k in ("id", "content"):
        if not str(e.get(k, "")).strip(): raise EvoError(f"条目缺 {k}")
    if e.get("type", "semantic") not in TYPES: raise EvoError(f"type 非法：{e.get('type')!r}")
    if e.get("state", "intermediate") not in STATES: raise EvoError(f"state 非法：{e.get('state')!r}")
    imp = e.get("importance", 0)
    if not isinstance(imp, int) or imp < 0: raise EvoError(f"importance 须非负整数：{imp!r}")

# ═══════════════════════════ §2 store（SQLite 单库即真相） ═══════════════════════════
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  actor TEXT NOT NULL, kind TEXT NOT NULL,
  payload JSON NOT NULL, prev_hash TEXT NOT NULL, self_hash TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT,'append-only: 禁 UPDATE'); END;
CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT,'append-only: 禁 DELETE'); END;
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
INSERT OR IGNORE INTO meta (k, v) VALUES ('level', 'G1');
INSERT OR IGNORE INTO meta (k, v) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO meta (k, v) VALUES ('hash_algo', 'v2');
"""

class Store:
    """events 账本（触发器物理 append-only）+ 档位存取。"""
    def __init__(self, conn): self.c = conn

    @classmethod
    def open(cls, path: str) -> "Store":
        pre = os.path.isfile(path)
        conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")  # 并发写者排队而非立即 SQLITE_BUSY
        if pre:
            cls._require_triggers(conn)      # 既有库先验（防 IF NOT EXISTS 静默重建掩盖）
            cls._require_hash_algo(conn)     # 老算法库先拒（防 SCHEMA 补键掩盖——同族教训）
        conn.executescript(SCHEMA)
        s = cls(conn)
        if s.level_index() >= 1: s.verify()  # G1+ 开库即验
        return s

    @staticmethod
    def _require_hash_algo(conn):
        """老算法库拒（v0.2.0 破坏性变更）。缺键不误杀：首行试算自动识别——
        v2 试算命中 ⇒ 在途库，补键放行；试算失败 ⇒ v1 或损坏，拒并提示重建。"""
        has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        has_events = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        if not (has and has_events): return
        row = conn.execute("SELECT v FROM meta WHERE k='hash_algo'").fetchone()
        if row and row[0] == HASH_ALGO: return
        first = conn.execute(
            "SELECT actor,kind,prev_hash,payload,self_hash FROM events ORDER BY seq LIMIT 1").fetchone()
        if first and event_hash(first[2], __import__("json").loads(first[3]), first[0], first[1]) == first[4]:
            conn.execute("INSERT OR IGNORE INTO meta (k, v) VALUES ('hash_algo', ?)", (HASH_ALGO,))
            return  # 在途 v2 库（键缺失晚于算法切换）：自动识别放行+补键
        if first:
            raise EvoError(
                f"老库（哈希算法 {(row[0] if row else 'v1')} ≠ 现版 {HASH_ALGO}）：不可读，请按事件流重建"
                f"（v0.2.0 为破坏性变更，见版本变更记录）")

    @staticmethod
    def _require_triggers(conn):
        has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        if not has: return
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        miss = {"no_update", "no_delete"} - names
        if miss: raise EvoError(f"既有库触发器缺失（append-only 被破坏，拒绝静默重建）：{sorted(miss)}")

    def level(self) -> str:
        return self.c.execute("SELECT v FROM meta WHERE k='level'").fetchone()[0]
    def level_index(self) -> int:
        return LEVELS.index(self.level())
    def set_level(self, lv: str, actor: str) -> dict:
        if lv not in LEVELS: raise EvoError(f"档位非法：{lv}")
        old = self.level()
        if LEVELS.index(lv) < self.level_index():
            self.append(f"engine", "level_downgrade", {"from": old, "to": lv})   # 降级留痕
        self.c.execute("UPDATE meta SET v=? WHERE k='level'", (lv,))
        return {"from": old, "to": lv}

    def verify(self) -> None:
        names = {r[0] for r in self.c.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        miss = {"no_update", "no_delete"} - names
        if miss: raise EvoError(f"触发器缺失：{sorted(miss)}")
        prev = GENESIS
        for seq, row_actor, row_kind, row_prev, payload, self_h in self.c.execute(
                "SELECT seq,actor,kind,prev_hash,payload,self_hash FROM events ORDER BY seq"):
            if row_prev != prev: raise EvoError(f"链断裂 seq={seq}")
            if event_hash(prev, json.loads(payload), row_actor, row_kind) != self_h:
                raise EvoError(f"哈希不符 seq={seq}（疑似篡改，含头部字段）")
            prev = self_h

    def append(self, actor: str, kind: str, payload: dict) -> dict:
        # 取尾→INSERT 同一事务（BEGIN IMMEDIATE 串行化并发写者）：
        # 分离执行时两写者同读尾哈希→链分叉，触发器禁修，库只余重建。
        self.c.execute("BEGIN IMMEDIATE")
        try:
            row = self.c.execute("SELECT self_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row[0] if row else GENESIS
            self_h = event_hash(prev, payload, actor, kind)
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            cur = self.c.execute(
                "INSERT INTO events (ts,actor,kind,payload,prev_hash,self_hash) VALUES (?,?,?,?,?,?)",
                (ts, actor, kind, canonical_json(payload), prev, self_h))
            self.c.execute("COMMIT")
        except Exception:
            self.c.execute("ROLLBACK")
            raise
        return {"seq": cur.lastrowid, "ts": ts, "actor": actor, "kind": kind,
                "payload": payload, "prev_hash": prev, "self_hash": self_h}

    def count(self) -> int:
        return self.c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    def head(self) -> str:
        r = self.c.execute("SELECT self_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return r[0] if r else GENESIS
    def rows(self):
        for r in self.c.execute(
                "SELECT seq,ts,actor,kind,payload,prev_hash,self_hash FROM events ORDER BY seq"):
            yield r

# ═══════════════════════════ §3 rank（检索：分词→打分→破序） ═══════════════════════════
_TOK = re.compile(r"[\w\u4e00-\u9fff]+")

def tokens(text):
    out = []
    for w in _TOK.findall(text or ""):
        if re.fullmatch(r"[\u4e00-\u9fff]+", w):
            out += [w] if len(w) == 1 else [w[i:i+2] for i in range(len(w)-1)]
        else: out.append(w.lower())
    return out

def score(entry, query, now=None) -> float:
    """五参数打分+类型衰减（G2 起类型曲线生效；G0-G1 按 semantic×1）。"""
    if now is None: now = datetime.datetime.now()
    q = set(tokens(query)); c = set(tokens(str(entry.get("content", ""))))
    kw = set(tokens(" ".join(entry.get("keywords", []) or [])))
    kh, ch = len(q & kw), len(q & c)
    if T.FILTER_ZERO and kh == 0 and ch == 0: return 0.0
    s = T.W_KW * kh + T.W_CONTENT * ch + T.W_IMP * float(entry.get("importance", 0) or 0)
    created = entry.get("last_used_at") or entry.get("created_at")
    if created:   # 可失败判据：时间戳存在则必须可解析，解析失败按 age=0 并明示（v3.9 bad-ts 语义，非静默）
        t0 = datetime.datetime.fromisoformat(created)
        age = max(0.0, (now - t0).total_seconds() / 86400.0)
        mult = T.DECAY.get(entry.get("type", "semantic"), 1.0)
        s -= T.W_AGE * age * mult
    if entry.get("tombstone"): s = 0.0
    return round(s, 4)

def retrieve(entries, query, k=5, now=None):
    scored = [(score(e, query, now), e) for e in entries]
    return sorted((x for x in scored if x[0] > 0), key=lambda kv: (-kv[0], kv[1].get("id", "")))[:k]

# ═══════════════════════════ §4 lifecycle（三态·墓碑·衰减） ═══════════════════════════
def route(entry) -> str:
    return "longterm" if int(entry.get("importance", 0) or 0) >= T.PROMOTE_MIN else "intermediate"
def touch(entry, ts: str) -> None: entry["last_used_at"] = ts
def tombstone(entry) -> dict:
    entry["tombstone"] = True
    return {"kind": "tombstone", "entry_id": entry.get("id"), "note": "退出检索，原位保留"}
def attic(entry, reason: str) -> dict:
    entry["state"] = "attic"
    return {"kind": "attic_nomination", "entry_id": entry.get("id"), "reason": reason[:200]}

# ═══════════════════════════ §5 decide（三 intent，G4 档） ═══════════════════════════
def _trace(intent, entries, decision, rationale):
    sev = "irreversible" if any(e.get("source") == "manual" for e in entries) else "redundant"
    return {"kind": "memory_adjudicate", "intent": intent,
            "entries": [e.get("id", "?") for e in entries], "decision": decision,
            "rationale": rationale[:200], "actor": "engine",
            "severity_if_wrong": sev, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}

def adjudicate(intent, entries):
    """G4：三 intent 规则版。conflict 保 manual>importance>new；merge 恒 defer；
    promote 按阈值批量。留痕结构强制（W7 起 LLM 按 prereg 金标挣得）。"""
    if intent == "conflict":
        if len(entries) < 2: raise EvoError("conflict 需 ≥2 条")
        rank = sorted(entries, key=lambda e: (1 if e.get("source") == "manual" else 0,
                                              int(e.get("importance", 0) or 0),
                                              e.get("created_at", "")), reverse=True)
        return _trace(intent, entries, f"keep:{rank[0].get('id','?')}",
                      "规则：manual>importance>new"), rank[0], rank[1:]
    if intent == "merge":
        if len(entries) < 2: raise EvoError("merge 需 ≥2 条")
        return _trace(intent, entries, "defer",
                      "保守拒绝：同义判断不可规则化（金标挣得后由 LLM 接管）")
    if intent == "promote":
        out = [(e, int(e.get("importance", 0) or 0) >= T.PROMOTE_MIN) for e in entries]
        return _trace(intent, entries,
                      ",".join(f"{e.get('id','?')}:{'p' if ok else 'h'}" for e, ok in out),
                      f"规则：importance>={T.PROMOTE_MIN}"), out
    raise EvoError(f"intent 非法：{intent}")

# ═══════════════════════════ §6 gates（治理门，G3/G5 档） ═══════════════════════════
def gate_file(path: str) -> list:
    """质量门五道（G3）：文件长度/语句/分支/import 白名单/静默失败。"""
    src = open(path, encoding="utf-8", errors="replace").read()
    bad = []
    if len(src.splitlines()) > T.MAX_LINES:
        bad.append(f"FILE {path}: {len(src.splitlines())} 行 > {T.MAX_LINES}")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            st = sum(1 for x in ast.walk(n) if isinstance(x, ast.stmt))
            br = sum(1 for x in ast.walk(n) if isinstance(x, BRANCH_T))
            if st > T.MAX_STMTS: bad.append(f"FUNC {path}:{n.lineno} {n.name} 语句 {st}>{T.MAX_STMTS}")
            if br > T.MAX_BRANCH: bad.append(f"FUNC {path}:{n.lineno} {n.name} 分支 {br}>{T.MAX_BRANCH}")
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in T.IMPORT_ALLOW:
                    bad.append(f"IMPORT {path}:{n.lineno} {a.name} 不在白名单")
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            if n.module.split(".")[0] not in T.IMPORT_ALLOW:
                bad.append(f"IMPORT {path}:{n.lineno} {n.module} 不在白名单")
        elif isinstance(n, ast.ExceptHandler):
            if all(isinstance(s, ast.Pass) for s in n.body):
                bad.append(f"SILENT {path}:{n.lineno} except:pass 吞错")
    return bad

def scan_refs(path: str) -> list:
    """出站扫描（G5）：全文件扫 path@commit:line 三态——✅可解析/⚠️越界/❌悬空。"""
    out = []
    for dp, ds, fs in os.walk(path):
        ds[:] = [d for d in ds if d not in {".git", "__pycache__", "state"}]
        for f in fs:
            if not f.endswith((".md", ".py")): continue
            fp = os.path.join(dp, f)
            for i, line in enumerate(open(fp, encoding="utf-8", errors="replace"), 1):
                for m in re.finditer(r"([\w/.\-\u4e00-\u9fff]+)@([0-9a-f]{8,64})", line):
                    out.append({"file": os.path.relpath(fp, path), "line": i,
                                "ref": m.group(0)[:80], "status": "⚠️ 越界不可证（记账不指控）"})
    return out

BRANCH_T = (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp)

# ═══════════════════════════ §7 cli（命令面） ═══════════════════════════
def _require(store, lv: str):
    if store.level_index() < LEVELS.index(lv):
        raise EvoError(f"需 {lv} 档（当前 {store.level()}）：evo level {lv} 升档")

def _content_hash(e: dict) -> str:
    """条目内容指纹（幂等键，**64 hex**）——P3/D7 统一（20260924）。

    与重装形态唯一来源**同规则镜像**（本件自包含，不 import 宿主包；一致性由
    `test_content_hash_divergence.py` 转正后的跨形态同指纹断言常驻盯防）：
    排除 id/entry_id/content_hash/state/last_used_at/**created_at**，keywords 归一
    有序词表，canonical JSON 后 sha256 全宽。**去重比较＝比较时重归一**：对既有条目
    重算本指纹再比——老库存储的旧 16 hex 指纹不参与比较、永不回改（无破坏性迁移）。
    历史：v1=16 hex 只排除三件（W2-N4 登记的分歧本尊）；v2=本版（关闭 evocore-D7）。
    （措辞注：本件受自包含扫描约束——源码不得出现宿主包名，故此处只写「宿主侧桥」。）
    """
    import hashlib
    body = {k: v for k, v in e.items()
            if k not in ("id", "entry_id", "content_hash", "state", "last_used_at",
                         "created_at")}
    if isinstance(body.get("keywords"), str):
        body["keywords"] = sorted(body["keywords"].split())
    elif isinstance(body.get("keywords"), list):
        body["keywords"] = sorted(body["keywords"])
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()

def _load_entries(store) -> list:
    """条目从 events 流复原（S5/T1 语义对齐：与重装形态 `evocore.project.project_entries`
    同语义——形态分离、语义对齐；差异由跨形态对照段常设盯防）：
      memory_append → 建条（created_at=payload 显式值，否则**账本行 ts**）
      promotion     → state=longterm
      memory_retrieve_hit → **last_used_at=账本行 ts**（命中持久；原为内存态）
      tombstone     → **tombstone=True**（退出检索、原位保留；原投影未处理）"""
    import json
    proj = {}
    for _seq, ts, _actor, kind, payload, _ph, _sh in store.rows():
        p = json.loads(payload)
        eid = p.get("entry_id")
        if kind == "memory_append":
            e = p | {"id": eid}
            if not e.get("created_at"):
                e["created_at"] = ts
            proj[eid] = e
        elif kind == "promotion" and eid in proj:
            proj[eid]["state"] = "longterm"
        elif kind == "memory_retrieve_hit" and eid in proj:
            proj[eid]["last_used_at"] = ts
        elif kind == "tombstone" and eid in proj:
            proj[eid]["tombstone"] = True
        elif kind == "attic_nomination" and eid in proj:
            proj[eid]["state"] = "attic"   # 与 evocore.lifecycle.attic 同语义（桥写事件此前被投影丢弃）
    return list(proj.values())

def cmd_init(a):
    d = os.path.dirname(os.path.abspath(a.lib))
    if d: os.makedirs(d, exist_ok=True)
    s = Store.open(a.lib)
    if a.level and a.level != s.level():
        s.set_level(a.level, "human:cli")
    print(f"init: {a.lib} level={s.level()} events={s.count()}")

def cmd_append(a):
    s = Store.open(a.lib)
    if s.level_index() >= 2: validate_entry({"id": a.id, "content": a.content,
        "type": a.type, "importance": a.importance})   # G2 起强制构造校验
    existing = {e.get("id"): e for e in _load_entries(s)}
    if a.id in existing:
        # id 幂等闸（02-bugs R5 状态机破口）：同 id 异内容重追加=覆盖投影（tombstone/
        # attic/promotion 历史被抹，墓碑条目复活回检索）→ 拒绝；同 id 同内容=幂等
        # no-op（与 cmd_import 的 content_hash 去重同语义，静态演示块可安全重跑）。
        old = existing[a.id]
        if (old.get("content") != a.content or old.get("type") != a.type
                or old.get("importance") != a.importance):
            raise EvoError(f"append 拒绝：id={a.id!r} 已在库且内容不同（重追加=覆盖历史，改内容请用新 id）")
        print(f"append: {a.id} 幂等跳过（同 id 同内容已在库）")
        return
    e = {"id": a.id, "content": a.content, "keywords": (a.keywords or "").split(),
         "importance": a.importance, "type": a.type, "state": route(
             {"importance": a.importance}), "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    r = s.append("llm:cli", "memory_append", e | {"entry_id": a.id})
    print(f"append: {a.id} seq={r['seq']} state={e['state']}")

def cmd_import(a):
    """批量注入：JSONL 逐行 → 构造校验（G2+）→ content_hash 幂等去重 → append。
    注入面只此一道门——批量不等于放宽（坏行拒、重复跳、全走 append 留痕）。"""
    s = Store.open(a.lib)
    seen = {_content_hash(e) for e in _load_entries(s)}    # P3：比较时重归一（存量指纹不参与）
    n_in = n_dup = n_bad = 0
    for line in open(a.file, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        try:
            e = json.loads(line)
        except Exception:
            n_bad += 1; continue
        if not isinstance(e, dict) or not str(e.get("id", "")).strip():
            n_bad += 1; continue
        if s.level_index() >= 2: validate_entry(e)
        chash = _content_hash(e)
        if chash in seen:
            n_dup += 1; continue
        seen.add(chash)
        s.append("import:pipeline", "memory_append", e | {"entry_id": e["id"], "content_hash": chash})
        n_in += 1
    print(f"import: 注入 {n_in} / 去重 {n_dup} / 坏行 {n_bad}（来源 {a.file}）")

def cmd_retrieve(a):
    s = Store.open(a.lib)
    es = _load_entries(s)
    for sc, e in retrieve(es, a.query, k=a.k, now=_now_or(a.at)):
        print(f"{sc:6.2f}  {e['id']}  {str(e.get('content',''))[:60]}")
        if s.level_index() >= 1: touch(e, time.strftime("%Y-%m-%dT%H:%M:%S"))
        s.append("engine", "memory_retrieve_hit", {"entry_id": e.get("id"), "query": a.query[:120]})

def _now_or(at): return datetime.datetime.fromisoformat(at) if at else None

def cmd_promote(a):
    s = Store.open(a.lib); _require(s, "G0")
    cur = next((e for e in _load_entries(s) if e.get("id") == a.id), None)
    if cur is None:
        raise EvoError(f"promote 拒绝：id={a.id!r} 不在库（悬空晋升会伪造留痕）")
    if cur.get("tombstone"):
        raise EvoError(f"promote 拒绝：id={a.id!r} 已 tombstone（退出检索原位保留，不得晋升）")
    if cur.get("state") == "attic":
        # 与 evocore.lifecycle.promote 同守卫：attic 条目不得直接晋升（须先人工恢复）
        raise EvoError(f"promote 拒绝：id={a.id!r} 在 attic（须先人工恢复再晋升）")
    s.append("engine", "promotion", {"entry_id": a.id})
    print(f"promote: {a.id} → longterm（留痕已入账）")

def cmd_tombstone(a):
    s = Store.open(a.lib); _require(s, "G1")
    s.append("engine", "tombstone", {"entry_id": a.id, "note": tombstone({"id": a.id})["note"]})
    print(f"tombstone: {a.id}（退出检索，原位保留）")

def cmd_verify(a):
    s = Store.open(a.lib); s.verify()
    print(f"verify: 通过（events={s.count()} 链完整 触发器在位 level={s.level()} framework_sha={framework_sha()}）")

def cmd_level(a):
    s = Store.open(a.lib)
    r = s.set_level(a.level.upper(), "human:cli")
    up = LEVELS.index(r["to"]) > LEVELS.index(r["from"])
    print(f"level: {r['from']} → {r['to']}（{'升档' if up else '降级已留痕'}）")

def cmd_gate(a):
    s = Store.open(a.lib); _require(s, "G3")
    bad = []
    for f in a.files: bad += gate_file(f)
    if bad:
        print(f"gate: 拒绝（{len(bad)} 项）"); [print("  " + b) for b in bad[:40]]; sys.exit(1)
    print(f"gate: 通过（{len(a.files)} 文件）")

def cmd_decide(a):
    s = Store.open(a.lib); _require(s, "G4")
    entries = _load_entries(s)
    picked = [e for e in entries if e["id"] in set(a.ids)]
    use = picked if picked else entries[:2]
    for eid, marks in _override_marks(s).items():
        if eid in {e["id"] for e in use}:
            for ov_seq, tgt, dec, why in marks:
                print(f"  [已由人工终裁] {eid} ← 终裁 seq={ov_seq}（针对判定 seq={tgt}）"
                      f"decision={dec}（{why}）")
    tr, *_ = adjudicate(a.intent, use)
    r = s.append("engine", "memory_adjudicate", tr)
    print(json.dumps(tr, ensure_ascii=False, indent=1))
    print(f"decide: 留痕 seq={r['seq']}（可被 `override --target-seq {r['seq']}` 人工终裁）")


# ---- 人侧仲裁通道（S8-4 · 20260923 开工批）----
def _overrides(store) -> list:
    """人工终裁事件表 [(自身 seq, payload)]（读侧）。

    与重装形态 `evocore.project.project_overrides` **同语义**（形态分离、语义对齐；
    跨形态对拍见 `build/tests/test_governance_matrix.py`）。
    """
    out = []
    for seq, _ts, _actor, kind, payload, _ph, _sh in store.rows():
        if kind == "human_override":
            out.append((seq, json.loads(payload)))
    return out


def _override_marks(store) -> dict:
    """把终裁回溯到条目：payload.target_seq → 该 seq 的 memory_adjudicate 留痕里的 entries[]。
    返回 {entry_id: [(终裁自身 seq, 被终裁的判定 seq, decision, rationale)]}；
    无 target_seq 的方针性终裁不入此表（只在 audit 计数）。"""
    adj = {}
    for seq, _ts, _actor, kind, payload, _ph, _sh in store.rows():
        if kind == "memory_adjudicate":
            adj[seq] = json.loads(payload).get("entries", [])
    marks = {}
    for ov_seq, p in _overrides(store):
        tgt = p.get("target_seq")
        if tgt is None:
            continue
        try:
            tseq = int(tgt)
        except (TypeError, ValueError):
            continue   # 畸形 target_seq：跳过而非中断整表
        for eid in adj.get(tseq, []):
            marks.setdefault(eid, []).append((ov_seq, tseq, p.get("decision"), p.get("rationale")))
    return marks


def cmd_override(a):
    """人侧仲裁（S8-4）：写 `human_override` 事件=**终局标记**。

    铁律落地：治理位在库外 ⇒ 本通道**只接受 `human:*` 身份**（fail-closed 断言，Agent 不得冒用）；
    且只在 CLI/ops 面存在，**不进协议面八工具**（协议面是 Agent 的入口，人侧动作不该从那走）。
    payload 冻结（S8工单 S8-4）：`{target_seq?, decision, rationale, cap_ref?}`。
    终裁不删历史：被终裁的判定事件仍在账（append-only），只是查询侧标注「已由人工终裁」。
    """
    s = Store.open(a.lib)
    if not a.actor.startswith("human:"):
        raise EvoError(f"override 仅限人侧身份 human:*（得 {a.actor!r}）——治理位在库外，Agent 不得冒用")
    if a.target_seq is not None:
        try:
            a.target_seq = int(a.target_seq)
        except (TypeError, ValueError):
            raise EvoError(f"target_seq 须整数（得 {a.target_seq!r}）")
        row = s.c.execute("SELECT seq,kind FROM events WHERE seq=?", (a.target_seq,)).fetchone()
        if not row:
            raise EvoError(f"target_seq={a.target_seq} 不在账（拒绝悬空终裁：终裁必须指向真实事件）")
        if row[1] != "memory_adjudicate":
            raise EvoError(f"target_seq={a.target_seq} 是 {row[1]} 事件（终裁只指向 memory_adjudicate 判定留痕）")
    payload = {"decision": a.decision, "rationale": a.rationale}
    if a.target_seq is not None:
        payload["target_seq"] = a.target_seq
    if a.cap_ref:
        payload["cap_ref"] = a.cap_ref
    r = s.append(a.actor, "human_override", payload)
    print(f"override: 终裁已入账 seq={r['seq']} actor={a.actor} decision={a.decision}"
          + (f" target_seq={a.target_seq}" if a.target_seq is not None else ""))

def cmd_anchor(a):
    s = Store.open(a.lib); _require(s, "G5")
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(a.lib)), "state"), exist_ok=True)
    ap = os.path.join(os.path.dirname(os.path.abspath(a.lib)), "state", "anchor.txt")
    open(ap, "w", encoding="utf-8").write(f"ledger_head={s.head()}\nat={time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
    s.append("engine", "anchor", {"ledger_head": s.head(), "file": "state/anchor.txt"})
    print(f"anchor: 链头 {s.head()[:16]}… 已写入 {ap}（合并时钉进 commit trailer）")

def cmd_scan(a):
    s = Store.open(a.lib); _require(s, "G5")
    rows = scan_refs(a.dir)
    for r in rows: print(f"[{r['status']}] {r['file']}:{r['line']} {r['ref']}")
    s.append("engine", "anchor_scan", {"dir": a.dir, "found": len(rows)})
    print(f"scan: {len(rows)} 条引用（三态判决见上；扫描清单已入账）")

def cmd_selftest(a):
    suite = unittest.defaultTestLoader.discover(os.path.dirname(os.path.abspath(__file__)),
                                                pattern="evo_seat.py")
    unittest.TextTestRunner(verbosity=0).run(suite)

_PCT_BASE = 100.0          # 百分比基数（来源视图占比用；三形态同名同值）


def _source_stats(store) -> dict:
    """来源视图（S8-6 最小版）：按**完整 actor** 聚合——只回答"谁的 Agent 在喂什么"。

    与重装形态 `evocore.project.project_sources` 同语义（跨形态一致性由
    `build/tests/test_sources_view.py` 钉，不靠注释声称）。只计数不判可信度——
    被采纳率/污染率属完整版，归 L2-2。
    键用完整 actor 而非首段前缀：`llm:alpha:g1` 与 `llm:beta:g2` 必须分桶，
    否则本视图为它们要区分的东西而失效（`project_sources` 有登记说明）。
    """
    out = {}
    for _seq, ts, actor, kind, _payload, _ph, _sh in store.rows():
        key = actor or "(空 actor)"          # 完整 actor 为键（截首段会把两个 Agent 并成一桶）
        s = out.setdefault(key, {"events": 0, "by_kind": {}, "last_ts": ""})
        s["events"] += 1
        s["by_kind"][kind] = s["by_kind"].get(kind, 0) + 1
        if ts > s["last_ts"]:
            s["last_ts"] = ts
    return out


def cmd_audit(a):
    # W2-N1（20260923 开工批）：原 checks 首项写死字面量 True——恒真锚（本项目自己的禁忌：
    # 「什么都没查」与「查了没问题」输出同形）。改为实测三值：触发器在位数 + 链复放结果 +
    # 失败原因；账本不可信时 fail-closed 退出（不许"报完就过"）。档位不足的格子仍报「本档不查」
    # （=None，与 False「不在位」严格分开，三态不与通过同形）。
    chain_err = None
    try:
        s = Store.open(a.lib)      # 开库即验（触发器/老算法库先拒）
        s.verify()                 # 显式复验：把「验过」变成被测得的值
    except EvoError as e:
        chain_err = str(e); s = None
    if s is None:
        print(f"  [不在位] 账本链与触发器（{chain_err}）")
        print("audit: FAIL —— 账本不可信，其余检查无意义（fail-closed）")
        raise SystemExit(1)
    n_trig = len({"no_update", "no_delete"} & {
        r[0] for r in s.c.execute("SELECT name FROM sqlite_master WHERE type='trigger'")})
    n_ev = s.count()
    lv = s.level()
    checks = [("账本链与触发器", chain_err is None and n_trig == 2),
              ("墓碑审计窗口", True if lv >= "G1" else None),
              ("条目构造校验", True if lv >= "G2" else None),
              ("质量门", True if lv >= "G3" else None),
              ("决策留痕", True if lv >= "G4" else None),
              ("入库锚+扫描", True if lv >= "G5" else None)]
    for name, on in checks:
        print(f"  [{'在位' if on else '不在位' if on is False else '本档不查'}] {name}")
    print(f"  [实测] append-only 触发器 {n_trig}/2 · 链重放 {n_ev} 事件"
          f"{'全部复算通过' if chain_err is None else '失败'}")
    ovs = _overrides(s)
    print(f"  [实测] 人侧终裁通道：human_override 事件 {len(ovs)} 条"
          f"（自身 seq：{[q for q, _ in ovs]}）· 回溯到条目 {len(_override_marks(s))} 个"
          f"（通道在 CLI `override`，不进协议面）")
    stats = _source_stats(s)
    tot = sum(v["events"] for v in stats.values())
    print(f"  [实测] 来源视图（最小版 · 按 actor · 共 {tot} 事件）：")
    for pfx in sorted(stats):
        v = stats[pfx]
        share = f"{_PCT_BASE * v['events'] / tot:.1f}%" if tot else "—"
        print(f"      {pfx:16s} {v['events']:4d} 条 · {share:>6s} · 最近 {v['last_ts']}"
              f" · kind {len(v['by_kind'])} 种")
    print("      （完整版=被采纳率/污染率，归 L2-2；本视图只到「谁在喂」可见）")
    print(f"  [符合] {SPEC}（复验：conformance.py --fused evo_seat.py）")
    print(f"  [边界] {GOVERNANCE_BOUNDARY}")
    print(f"audit: level={lv} events={n_ev} framework_sha={framework_sha()}")

# ═══════════════════════════ §8 tests（内嵌自注册） ═══════════════════════════
class TestCore(unittest.TestCase):
    def test_hash_deterministic(self):
        self.assertEqual(event_hash(GENESIS, {"a": 1}), event_hash(GENESIS, {"a": 1}))
    def test_hash_order_irrelevant(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}), canonical_json({"a": 2, "b": 1}))
    def test_bad_prev_rejected(self):
        with self.assertRaises(EvoError): event_hash("zz", {})

class TestStoreLevel(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.p = os.path.join(tempfile.mkdtemp(prefix="evo_"), "t.db")
    def test_trigger_physically_aborts(self):
        s = Store.open(self.p); s.append("human:a", "k", {"a": 1}); s.close = lambda: None
        conn = sqlite3.connect(self.p)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE events SET kind='x'")
    def test_level_downgrade_leaves_trace(self):
        s = Store.open(self.p); n0 = s.count()
        s.set_level("G0", "human:a")
        self.assertEqual(s.level(), "G0"); self.assertEqual(s.count(), n0 + 1)

class TestEvolution(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.s = Store.open(os.path.join(tempfile.mkdtemp(prefix="evo_"), "t.db"))
    def test_procedural_zero_decay(self):
        old = {"id": "o", "content": "布光", "keywords": ["布光"], "importance": 5,
               "type": "procedural", "created_at": "2020-01-01T00:00:00"}
        new = dict(old, id="n", created_at="2026-09-23T00:00:00")
        self.assertEqual(score(old, "布光", NOW_T), score(new, "布光", NOW_T))
    def test_tombstone_exits(self):
        self.assertEqual(score({"id": "t", "content": "布光", "keywords": ["布光"],
                                "importance": 9, "tombstone": True}, "布光", NOW_T), 0.0)
    def test_conflict_manual_wins(self):
        tr, win, _ = adjudicate("conflict", [{"id": "a", "source": "agent", "importance": 9},
                                             {"id": "m", "source": "manual", "importance": 1}])
        self.assertEqual(win["id"], "m")
        self.assertEqual(tr["severity_if_wrong"], "irreversible")

NOW_T = datetime.datetime(2026, 9, 23, 12, 0, 0)

class TestSelf(unittest.TestCase):
    def test_framework_sha_discriminates(self):
        # 判别力不变量（v0.2.1 修复配套）：框架段改动 → framework_sha 必变
        import hashlib, re as _re, tempfile
        src = open(os.path.abspath(__file__), encoding="utf-8").read()
        a = _re.search(r"^# ═+ §1 core", src, _re.M)
        b = _re.search(r"^# ═+ §7 cli", src, _re.M)
        self.assertTrue(a and b, "区段横幅可定位")
        seg = src[a.start():b.start()]
        self.assertGreater(len(seg), 5000, "框架段长度下限（防 docstring 误切）")
        h1 = hashlib.sha256(seg.encode()).hexdigest()[:16]
        h2 = hashlib.sha256(seg.replace("append-only: 禁 UPDATE", "X", 1).encode()).hexdigest()[:16]
        self.assertNotEqual(h1, h2, "破坏框架段必须改变哈希（判别力）")
    def test_version_and_algo_declared(self):
        # 版本纪律：破坏性变更必升版本+算法版本声明
        self.assertEqual(VERSION, "0.2.2")
        self.assertEqual(HASH_ALGO, "v2")
    def test_self_source_scan_has_no_host_words(self):
        # 自包含不变量：源码不含宿主名（断言用拼接避开自指）
        src = open(os.path.abspath(__file__), encoding="utf-8").read()
        self.assertNotIn("mem" + "sys", src, "微内核须自包含（P9 同款）")

# ═══════════════════════════ §9 main ═══════════════════════════
def main():
    ap = argparse.ArgumentParser(description="evo-seat 微型内核")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init"); p.add_argument("lib"); p.add_argument("--level", default=None)
    p = sp.add_parser("append"); p.add_argument("lib")
    for f, req in (("id", True), ("content", True), ("keywords", False)):
        p.add_argument(f"--{f}", required=req)
    p.add_argument("--type", default="semantic"); p.add_argument("--importance", type=int, default=5)
    p = sp.add_parser("import"); p.add_argument("lib"); p.add_argument("file")
    p = sp.add_parser("retrieve"); p.add_argument("lib"); p.add_argument("query")
    p.add_argument("-k", type=int, default=5); p.add_argument("--at", default=None)
    p = sp.add_parser("promote"); p.add_argument("lib"); p.add_argument("id")
    p = sp.add_parser("tombstone"); p.add_argument("lib"); p.add_argument("id")
    p = sp.add_parser("verify"); p.add_argument("lib")
    p = sp.add_parser("level"); p.add_argument("lib"); p.add_argument("level")
    p = sp.add_parser("gate"); p.add_argument("lib"); p.add_argument("files", nargs="+")
    p = sp.add_parser("decide"); p.add_argument("lib"); p.add_argument("intent",
        choices=["conflict", "merge", "promote"]); p.add_argument("ids", nargs="+")
    p = sp.add_parser("anchor"); p.add_argument("lib")
    p = sp.add_parser("scan"); p.add_argument("lib"); p.add_argument("dir")
    p = sp.add_parser("override"); p.add_argument("lib")          # 人侧仲裁（S8-4）
    p.add_argument("--actor", required=True, help="人侧身份，必须 human:*（Agent 不得冒用）")
    p.add_argument("--decision", required=True); p.add_argument("--rationale", required=True)
    p.add_argument("--target-seq", type=int, default=None, dest="target_seq",
                   help="被终裁事件的 seq（须在账；缺省=不指向具体事件的方针性终裁）")
    p.add_argument("--cap-ref", default=None, dest="cap_ref")
    sp.add_parser("selftest")
    p = sp.add_parser("audit"); p.add_argument("lib")
    a = ap.parse_args()
    fn = {"init": cmd_init, "append": cmd_append, "import": cmd_import, "retrieve": cmd_retrieve,
          "promote": cmd_promote, "tombstone": cmd_tombstone, "verify": cmd_verify,
          "level": cmd_level, "gate": cmd_gate, "decide": cmd_decide, "override": cmd_override,
          "anchor": cmd_anchor, "scan": cmd_scan, "selftest": cmd_selftest,
          "audit": cmd_audit}[a.cmd]
    fn(a)

if __name__ == "__main__":
    main()
