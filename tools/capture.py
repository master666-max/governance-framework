# -*- coding: utf-8 -*-
"""capture.py — 运行中自主捕获工具壳（条目140，可行性一档实施）
两段式的第一段：模型运行途中察觉"值得记"→本工具写入 capture-inbox/（暂存区），
**不直接触账本**；入账由 session-mining 管线（sm_check→merge→append2）单点执行。
三问判据（--kind 必选即第一问/第三问自答，--why 即察觉理由留痕）：
  ①有新数字吗 ②有新裁决吗 ③有可锚原文吗 —— 全中才捕。
用法:
  py -X utf8 tools/capture.py --source <文件绝对路径> --line <行号> \
      --start "<逐字锚起>" --end "<逐字锚止>" --kind result \
      --why "<≤30字捕获理由>" [--untrusted] [--url <http来源>]
"""
import argparse, datetime, hashlib, json, os, sys
AUD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # W2-N8：仓根自定位（原写死绝对路径，换机/改名即失效）
INBOX = os.path.join(AUD, "capture-inbox")
KINDS = {"result", "verdict", "parameter", "method", "hypothesis"}
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--line", type=int, required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--kind", required=True, choices=sorted(KINDS))
    ap.add_argument("--why", required=True)
    ap.add_argument("--untrusted", action="store_true")
    ap.add_argument("--url", default="")
    a = ap.parse_args()
    if len(a.why) > 30: sys.exit("FAIL: 捕获理由 >30 字（先想清楚为什么值得记）")
    if a.untrusted and not (a.url or a.source.lower().startswith("http")):
        sys.exit("FAIL: untrusted 条目须带 --url 或 http 形态 source")
    if not os.path.exists(a.source): sys.exit(f"FAIL: 源不存在 {a.source}")
    lines = open(a.source, encoding="utf-8", errors="replace").readlines()
    if not (1 <= a.line <= len(lines)): sys.exit(f"FAIL: 行号越界 {a.line}/{len(lines)}")
    text = lines[a.line - 1].rstrip("\r\n")
    i = text.find(a.start)
    j = text.find(a.end, i + len(a.start)) if i >= 0 else -1
    if i < 0 or j < 0: sys.exit("FAIL: 锚未命中（start 未找到或 end 不在其后）——三问第三问不过，不捕")
    quote = text[i:j + len(a.end)]
    if len(quote) > 200: sys.exit(f"FAIL: 摘录 {len(quote)} 字 >200")
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    eid = "CAP-" + now[:10].replace("-", "") + "-" + hashlib.sha256(quote.encode("utf-8")).hexdigest()[:6]
    entry = {
        "experiment_id": eid, "source_file": a.source, "line": a.line,
        "start_anchor": a.start, "end_anchor": a.end, "verbatim_quote": quote,
        "claim_type": a.kind, "capture_why": a.why, "untrusted": a.untrusted,
        "url": a.url, "captured_at": now, "status": "open",
    }
    os.makedirs(INBOX, exist_ok=True)
    out = os.path.join(INBOX, f"cap-{now[:10]}.jsonl")
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"已捕获 {eid} → {os.path.relpath(out, AUD)}")
    print(f"  kind={a.kind} untrusted={a.untrusted} 摘录{len(quote)}字 | {quote[:60]}…")
main()
