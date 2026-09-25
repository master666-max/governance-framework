# repair_log_order.py — INCREMENTAL-LOG 条目顺序结构修复（2026-09-17）
# 事实：59 条全在、各恰一次；错乱=插入锚点踩踏致顺序错乱。修复=按编号稳定重排。
# 安全：仅重排不改行；修复前后行数必须一致；条目数必须=59 且编号连续 1-59。
import os
import re

P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "INCREMENTAL-LOG.md")  # W2-N8：自定位
lines = open(P, encoding="utf-8").read().splitlines(keepends=True)

# 定位所有条目头
heads = [(i, int(re.match(r"^## 条目 (\d+)", l).group(1)))
         for i, l in enumerate(lines) if l.startswith("## 条目")]
nums = [n for _, n in heads]
print("条目数:", len(nums), " 编号范围:", min(nums), "-", max(nums))
assert len(nums) == len(set(nums)), "存在重复条目！中止"
assert sorted(nums) == list(range(1, len(nums) + 1)), "编号不连续！中止"

pre = lines[: heads[0][0]]
segs = {n: lines[i:j] for (i, n), (j, _) in zip(heads, heads[1:] + [(len(lines), None)])}

rebuilt = list(pre)
for n in sorted(segs):
    rebuilt += segs[n]

before = len(lines)
after = len(rebuilt)
assert before == after, f"行数不一致 {before}!={after}"
open(P, "w", encoding="utf-8", newline="").writelines(rebuilt)
print(f"重排完成：{before} 行 → {after} 行（纯重排零改写）")

# 自验：新文件条目顺序应严格递增
heads2 = [(i, int(re.match(r"^## 条目 (\d+)", l).group(1)))
          for i, l in enumerate(open(P, encoding="utf-8").readlines()) if l.startswith("## 条目")]
seq = [n for _, n in heads2]
print("修复后顺序:", "OK 严格递增" if seq == sorted(seq) else "仍乱！", "首尾:", seq[0], seq[-1])
