# -*- coding: utf-8 -*-
"""bench_evocore.py — evocore 检索性能观测点（S1v2 · T6；总工单 G6/P10）

定位：**只观测不设门**（知识库场景性能非首害——G6 判"登记不立门"）。
输出三档（默认 1k/10k/100k）的 retrieve 中位延迟 + 线性度；读数供触发器判定：
  触发器（2026-09-23 登记）：10k 库单查 > 200 ms 或 100k 库 > 2 s 才动优化（如分词缓存）。
用法: py -X utf8 tools/bench_evocore.py [--sizes 1000,10000,100000] [--k 5] [--repeat 5] [--seed 7]
"""
import argparse
import datetime
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
from evocore import retrieve  # noqa: E402

WORDS = ["偏好", "深色", "主题", "缓存", "索引", "衰减", "检索", "排序", "模型", "调度", "图谱", "嵌入"]
NOW = datetime.datetime(2026, 9, 21, 12, 0, 0)


def make_entries(n: int, seed: int):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        out.append({"id": f"e{i:06d}",
                    "content": " ".join(rng.sample(WORDS, 5)),
                    "keywords": rng.sample(WORDS, 2),
                    "importance": rng.randint(0, 10),
                    "type": rng.choice(["episodic", "semantic", "procedural"]),
                    "created_at": f"2026-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}T00:00:00"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1000,10000,100000")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    print(f"bench_evocore · k={a.k} · repeat={a.repeat} · seed={a.seed}（下界=中位；线性度=ns/条）")
    print(f"{'条目数':>8} | {'中位 ms':>9} | {'每条 ns':>9} | {'top1':>8}")
    for n in [int(x) for x in a.sizes.split(",")]:
        ents = make_entries(n, a.seed)
        retrieve(ents, "偏好 深色", k=a.k, now=NOW)          # 预热（import/编译效应不计入）
        ts = []
        for _ in range(a.repeat):
            t0 = time.perf_counter()
            got = retrieve(ents, "偏好 深色", k=a.k, now=NOW)
            ts.append(time.perf_counter() - t0)
        med = statistics.median(ts)
        print(f"{n:>8} | {1000 * med:>9.2f} | {1e9 * med / n:>9.1f} | {got[0][1]['id'] if got else '-'}")
    print(f"注：线性度≈常数（每条 ns 稳定即 O(n) 扫描符合预期）；触发器见文件头。")


if __name__ == "__main__":
    main()
