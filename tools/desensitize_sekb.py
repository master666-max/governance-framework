# -*- coding: utf-8 -*-
"""desensitize_sekb.py — 发布三副本内部 agent 线名词级脱敏（条目136，用户令）
映射（审计区留底，内部件不脱敏，仅发布/源三副本）：
  混元→线A  豆包→线B  衔尾蛇→线C  迷深→线M
范围：sekb-plugin/ sekb-dsh-package/ skill/ 的 .md .py .sh .json
不改动 git 历史；VKPS/主区/审计区等语境词本轮不动（呈报待裁）。
用法: py -X utf8 tools/desensitize_sekb.py [--dry]
"""
import os, sys
AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
MAP = {"混元": "线A", "豆包": "线B", "衔尾蛇": "线C", "迷深": "线M"}
ROOTS = [os.path.join(AUD, "sekb-plugin"), os.path.join(AUD, "sekb-dsh-package"), os.path.join(AUD, "skill")]
EXTS = {".md", ".py", ".sh", ".json"}
def main():
    dry = "--dry" in sys.argv
    total = 0
    for root in ROOTS:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules"}]
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in EXTS: continue
                fp = os.path.join(dirpath, fn)
                raw = open(fp, "rb").read()
                text = raw.decode("utf-8")
                n = 0
                for k, v in MAP.items():
                    n += text.count(k)
                    text = text.replace(k, v)
                if n:
                    total += n
                    print(f"{n:3d}  {os.path.relpath(fp, AUD)}")
                    if not dry:
                        open(fp, "wb").write(text.encode("utf-8"))
    print(f"{'[DRY] ' if dry else ''}替换合计: {total}")
main()
