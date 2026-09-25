# -*- coding: utf-8 -*-
"""code_quality_gate.py — 代码质量门（零依赖；《代码质量门配置单》v1 + S1v2 门⑥）
六道机械门（fail-closed：违规=退出码 1）：
  ① 文件长度：> MAX_LINES 拒（装配产物/存量豁免用 --legacy）
  ② 函数语句数：> MAX_STMTS 拒
  ③ 函数分支数（if/elif/for/while/except/and/or 计数）：> MAX_BRANCH 拒
  ④ 依赖白名单：import 仅许 标准库+显式允许（防幻觉依赖/slopsquatting，AI编程缺陷业界20%）
  ⑤ 静默失败：bare except:pass / except:pass（吞错）一律拒（业界"80%问题"的典型形态）
  ⑥ 安全专项（S1v2·G1/P1-P5）：eval/exec · os.system/os.popen · subprocess shell=True ·
     pickle/marshal 反序列化 · __import__ 非字面量 · 硬编码凭据字面量——拒；
     豁免=同行或上一行 `# sec-exempt: <理由>`（理由非空才生效，违规面留痕）
用法: py -X utf8 tools/code_quality_gate.py <file.py> [more.py] [--legacy] [--allow pkg1,pkg2]
      门④白名单=stdlib + 本仓模块（仓内实有件才放行）+ --allow（第三方）
      （--legacy=存量豁免：跳过门①⑥——既有大文件/既有 exec 站点不因新门重扫而翻旧账）
"""
import ast, os, re, sys

MAX_LINES = 900
MAX_STMTS = 80
MAX_BRANCH = 15
BRANCH_T = (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp)

# 门④ 白名单：Python 标准库（常用面）+ 本仓模块。第三方包必须 --allow 显式放行。
STDLIB = {
    "sys","os","re","json","hashlib","time","argparse","tempfile","shutil","pathlib",
    "datetime","math","random","csv","collections","itertools","functools","sqlite3",
    "ast","dataclasses","typing","enum","subprocess","urllib.parse","textwrap",
    "unittest","copy","io","unicodedata","statistics","uuid","zlib","base64","struct",
    "contextlib","warnings","logging","abc","types","inspect","operator","__future__","fnmatch","importlib","subprocess","sqlite3",
    "difflib",   # S1 补：stdlib 缺项（S1_verify_src 逐行对拍用；20260923 登记）
    "stat",      # W5 批补（20260924）：stdlib 缺项——测试件用 stat.S_* 判只读位；同"白名单缺 stdlib 件"家族
    "http",      # S4 补：stdlib 缺项（L2 服务件 --http 绑定用；20260923 登记）
    "queue", "threading", "socket", "urllib",   # S4 补：stdlib 缺项（MCP harness：超时读/端口/HTTP 客户端）
    "zipfile",   # S7 补：stdlib 缺项（发布件打包器）
    "glob",      # W2 批补（20260923）：stdlib 缺项——外仓复算工具用；同 坑11「白名单缺 stdlib 件」家族
}
DEFAULT_ALLOW = set()

# 门④ 本仓模块面（20260924 W5 批补）：上面注释写着"标准库 + 本仓模块"，但本仓模块此前
# **无处登记**——每次跑门都要手传 `--allow evocore,ledger,…`。手传的仪器等于没仪器：
# 忘传就一片红，久了就没人跑。名单以"仓内确有此件"为条件放行（见 _first_party()），
# 改名/删件后自动失效 ⇒ 不会留一条放行了不存在的名字的僵尸豁免。
FIRST_PARTY = ("evocore", "ledger", "gov_types", "capabilities", "hashes", "prereg",
               "mcp_client",                                              # build/tests 夹具
               "tunables", "retrieval", "lifecycle", "decision", "entry", "project",  # evocore 子件（按裸名导入）
               "bridge", "conformance", "boot_self")  # P1 补：自举账本件（audit-kit/boot_self.py）                                   # memsys 桥 / 一致性测试件
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FP_SEARCH = ("", "evocore", "audit-kit", "audit-kit/core", "audit-kit/ledger",
              "memsys", "build/tests")


def _first_party():
    """→ 当前在仓内真找得到的本仓模块名集合（改过名就不再放行）。"""
    out = set()
    for m in FIRST_PARTY:
        for d in _FP_SEARCH:
            if (os.path.isfile(os.path.join(_HERE, d, m + ".py"))
                    or os.path.isfile(os.path.join(_HERE, d, m, "__init__.py"))):
                out.add(m)
                break
    return out

def _imports(tree):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names: out.append((a.name, n.lineno))
        elif isinstance(n, ast.ImportFrom):
            if n.level == 0 and n.module:
                out.append((n.module, n.lineno))
            # 相对导入（level>0）= 本仓内模块，放行
        elif isinstance(n, ast.Call):   # 动态导入按 import 记（否则门④可被 import_module 绕过）
            f = getattr(n.func, "attr", "") if isinstance(n.func, ast.Attribute) else (
                n.func.id if isinstance(n.func, ast.Name) else "")
            base = getattr(n.func, "value", None)
            mod0 = base.id if isinstance(base, ast.Name) else ""
            if (f == "__import__" and not mod0) or (mod0 == "importlib" and f == "import_module"):
                if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    out.append((n.args[0].value.split(".")[0], n.lineno))
    return out

def _silent_catches(tree):
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler):
            body = n.body
            if all(isinstance(s, ast.Pass) for s in body):
                bad.append(n.lineno)
            elif len(body) == 1 and isinstance(body[0], ast.Continue) and n.type is None:
                bad.append(n.lineno)   # bare except: continue 同样吞错
    return bad

# ── 门⑥ 安全专项（S1v2 · G1/P1-P5）：危险构造 AST 检出 ──
_CRED_NAME = re.compile(r"(password|passwd|secret|api_?key|access_?key|auth_?token)", re.I)
_PLACEHOLDER = re.compile(r"(test|example|placeholder|dummy|redact|your|change_?me|<)", re.I)
_SEC_EXEMPT = re.compile(r"#\s*sec-exempt:\s*\S")

def _call_name(node):
    """调用名归一：Name / module.attr / module.sub.attr（其余 None）。"""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        if isinstance(f.value, ast.Name):
            return f"{f.value.id}.{f.attr}"
        if isinstance(f.value, ast.Attribute) and isinstance(f.value.value, ast.Name):
            return f"{f.value.value.id}.{f.value.attr}.{f.attr}"
    return None

_CALL_RULES = (
    ({"eval", "exec"}, "动态执行"),
    ({"os.system", "os.popen"}, "shell 执行"),
    ({"pickle.load", "pickle.loads", "marshal.load", "marshal.loads"}, "反序列化"),
)

def _from_import_aliases(tree):
    """from-import 别名表：local 名 → 完整限定名（`from os import system` 后裸调
    system() 必须还原成 os.system 参与门⑥匹配，否则整类形态绕过）。"""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            for a in n.names:
                if a.name != "*":
                    out[a.asname or a.name] = f"{n.module}.{a.name}"
    return out

def _call_sec_reason(node, aliases=None):
    """调用类安全规则 → 理由或 None。裸名先经 from-import 别名还原。"""
    name = _call_name(node)
    if name is None:
        return None
    if aliases and "." not in name:
        name = aliases.get(name, name)
    for names, why in _CALL_RULES:
        if name in names:
            return f"{name}() {why}"
    if name.startswith("subprocess.") and any(
            k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value for k in node.keywords):
        return f"{name}(shell=True) shell 注入面"
    if name == "__import__" and not (node.args and isinstance(node.args[0], ast.Constant)
                                     and isinstance(node.args[0].value, str)):
        return "__import__() 非字面量"
    return None

def _assign_sec_reason(node):
    """硬编码凭据规则（赋值名形似凭据 + 非占位字符串字面量）→ 理由或 None。"""
    if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)):
        return None
    val = node.value.value
    if len(val) < 6 or _PLACEHOLDER.search(val):
        return None
    for t in node.targets:
        ident = t.id if isinstance(t, ast.Name) else (t.attr if isinstance(t, ast.Attribute) else "")
        if ident and _CRED_NAME.search(ident):
            return f"硬编码凭据形态：{ident} = <字符串字面量>"
    return None

def _sec_hits(tree, src_lines):
    """返回 [(lineno, 说明)]；`# sec-exempt: 理由`（同行/上一行）豁免且不计入。"""
    hits = []
    aliases = _from_import_aliases(tree)
    for n in ast.walk(tree):
        why = _call_sec_reason(n, aliases) if isinstance(n, ast.Call) else _assign_sec_reason(n)
        if why is None:
            continue
        if (_SEC_EXEMPT.search(src_lines[n.lineno - 2] if n.lineno >= 2 else "")
                or _SEC_EXEMPT.search(src_lines[n.lineno - 1])):
            continue
        hits.append((n.lineno, why))
    return hits

def check(path, legacy, allow):
    src = open(path, encoding="utf-8", errors="replace").read()
    lines = len(src.splitlines())
    bad = []
    if lines > MAX_LINES and not legacy:
        bad.append(f"FILE {path}: {lines} 行 > {MAX_LINES}")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"FILE {path}: 语法错误 {e}"]
    # 门④ 依赖白名单
    allowed = STDLIB | DEFAULT_ALLOW | _first_party() | allow
    for mod, ln in _imports(tree):
        root = mod.split(".")[0]
        if mod in allowed or root in allowed: continue
        if root == path.replace("\\", "/").split("/")[-1].split(".")[0]: continue  # 本文件
        bad.append(f"IMPORT {path}:{ln} {mod} 不在白名单（幻觉依赖/slopsquatting 防：第三方须 --allow 显式放行）")
    # 门⑤ 静默失败
    for ln in _silent_catches(tree):
        bad.append(f"SILENT {path}:{ln} except:pass/continue 吞错（静默失败=业界80%问题形态）")
    # 门⑥ 安全专项（S1v2/G1）
    if not legacy:
        for ln, why in _sec_hits(tree, src.splitlines()):
            bad.append(f"SECURITY {path}:{ln} {why}（G1/P1-P5；合规站点用 `# sec-exempt: 理由` 登记）")
    # 门①②③
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s = sum(1 for x in ast.walk(n) if isinstance(x, ast.stmt))
            b = sum(1 for x in ast.walk(n) if isinstance(x, BRANCH_T))
            if s > MAX_STMTS:
                bad.append(f"FUNC {path}:{n.lineno} {n.name}: 语句 {s} > {MAX_STMTS}")
            if b > MAX_BRANCH:
                bad.append(f"FUNC {path}:{n.lineno} {n.name}: 分支 {b} > {MAX_BRANCH}")
    return bad

def main():
    argv = sys.argv[1:]
    legacy = "--legacy" in argv
    allow = set()
    i = 0
    while i < len(argv):   # 解析后 argv 只剩文件与旗标；--allow 缺值=用法错（fail-closed）
        a = argv[i]
        if a == "--allow":
            if i + 1 >= len(argv):
                print("用法错误：--allow 后缺包清单", file=sys.stderr); sys.exit(2)
            allow |= {x.strip() for x in argv[i+1].split(",")}
            del argv[i:i+2]
        elif a.startswith("--allow="):
            allow |= {x.strip() for x in a[len("--allow="):].split(",")}
            del argv[i]
        else:
            i += 1
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("用法: py -X utf8 tools/code_quality_gate.py <file.py> [...] [--legacy] [--allow pkg,...]\n"
              "空文件列表拒绝判「通过」——没查就说过 = fail-open（02-bugs R2-G1）", file=sys.stderr)
        sys.exit(2)
    all_bad = []
    for p in args:
        all_bad += check(p, legacy, allow)
    if all_bad:
        print(f"代码质量门：拒绝（{len(all_bad)} 项违规 / {len(args)} 文件）")
        for b in all_bad[:50]: print("  " + b)
        sys.exit(1)
    print(f"代码质量门：通过（{len(args)} 文件）")

if __name__ == "__main__":      # 无守卫时 import 本件即执行一次门（曾被测试收集器踩到）
    main()
