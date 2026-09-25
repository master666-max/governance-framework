# -*- coding: utf-8 -*-
"""mcp_client.py — MCP stdio 客户端 harness（S4/T5；零第三方依赖）

用途：①作为库（`from mcp_client import MCPClient`）供测试驱动服务件；
②作为脚本直跑=**验收主判据的机器面**（initialize → tools/list=8 → 八工具 happy path）。

实现：stdio=逐行 JSON-RPC；读线程+队列实现可超时的同步请求（Windows 管道上 select 不可用）。
用法（脚本）: py -X utf8 build/tests/mcp_client.py <server_dir> [--libs-root DIR]
"""
import argparse
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time

TOOLS8 = ["memory_append", "memory_retrieve", "memory_promote", "memory_tombstone",
          "memory_verify", "anchor", "scan", "adjudicate"]
PRINT_SNIPPET = 110        # 脚本模式打印载荷的截断长


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class MCPClient:
    """stdio MCP 客户端（spawn 服务件 → 逐行 JSON-RPC）。"""

    def __init__(self, argv, timeout=20.0, env=None):
        self.timeout = timeout
        self.p = subprocess.Popen([str(x) for x in argv], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", bufsize=1, env=env)
        self.q = queue.Queue()
        self.t = threading.Thread(target=self._reader, daemon=True)
        self.t.start()
        self._id = 0

    def _reader(self):
        for line in self.p.stdout:
            line = line.strip()
            if line:
                self.q.put(line)

    def _send(self, obj):
        self.p.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.p.stdin.flush()

    def request(self, method, params=None):
        self._id += 1
        mid = self._id
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                line = self.q.get(timeout=max(0.05, deadline - time.time()))
            except queue.Empty:
                continue
            msg = json.loads(line)
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"JSON-RPC error {msg['error'].get('code')}: {msg['error'].get('message')}")
                return msg["result"]
        raise TimeoutError(f"等待 {method} 响应超时")

    def raw(self, line):
        """发任意原始行（畸形输入测试用）；返回下一条带 id 的响应或 None（超时）。"""
        self._id += 1
        mid = self._id
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                msg = json.loads(self.q.get(timeout=max(0.05, deadline - time.time())))
            except queue.Empty:
                continue
            if msg.get("id") == mid or msg.get("error"):
                return msg
        return None

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def call_tool(self, name, arguments):
        r = self.request("tools/call", {"name": name, "arguments": arguments})
        text = r["content"][0]["text"]
        return (not r.get("isError")), json.loads(text), r.get("_meta", {})

    def close(self):
        try:
            self.p.stdin.close()
        except OSError:
            self.p.kill()        # 管道已断：走强杀清理（不吞错——静默失败门规）
            return
        self.p.terminate()
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.p.kill()


def _demo(server_dir, libs_root):
    """脚本模式：主判据机器面（initialize → tools/list → 八工具）。"""
    c = MCPClient([sys.executable, "-X", "utf8", os.path.join(server_dir, "server.py"),
                   "--libs-root", libs_root], env={**os.environ, "L2_GRANT": "g1"})
    init = c.request("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "harness"}})
    print(f"initialize: protocolVersion={init['protocolVersion']} server={init['serverInfo']['name']}"
          f" v{init['serverInfo']['version']}")
    c.notify("notifications/initialized")
    tools = c.request("tools/list")["tools"]
    names = [t["name"] for t in tools]
    print(f"tools/list: {len(names)} 件 = {names}")
    assert names == TOOLS8, "工具清单不符"
    steps = [("memory_append", {"lib": "demo.db", "id": "e1", "content": "玻璃材质 IOR 1.45",
                                "keywords": ["玻璃"], "type": "procedural", "importance": 8}),
             ("memory_append", {"lib": "demo.db", "id": "e2", "content": "三点布光 主光 45 度",
                                "keywords": ["布光"], "type": "procedural", "importance": 7}),
             ("memory_retrieve", {"lib": "demo.db", "query": "玻璃 材质", "k": 3}),
             ("memory_promote", {"lib": "demo.db", "id": "e1"}),
             ("memory_tombstone", {"lib": "demo.db", "id": "e2"}),
             ("memory_verify", {"lib": "demo.db"}),
             ("anchor", {"lib": "demo.db"}),
             ("scan", {"lib": "demo.db", "dir": "."}),
             ("adjudicate", {"lib": "demo.db", "intent": "merge", "ids": ["e1", "e2"]})]
    okn = 0
    for tool, args in steps:
        ok, payload, meta = c.call_tool(tool, args)
        okn += ok
        print(f"  [{'ok' if ok else 'FAIL'}] {tool} ms={meta.get('ms')} "
              f"{json.dumps(payload, ensure_ascii=False)[:PRINT_SNIPPET]}")
    c.close()
    print(f"client harness: {okn}/{len(steps)}（八工具路径）")
    return 0 if okn == len(steps) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("server_dir")
    ap.add_argument("--libs-root", default=None)
    a = ap.parse_args()
    libs = a.libs_root or os.path.join(a.server_dir, "libs")
    if not os.path.isfile(os.path.join(libs, "demo.db")):
        subprocess.run([sys.executable, "-X", "utf8", os.path.join(a.server_dir, "server.py"),
                        "init", "--libs-root", libs, "--lib", "demo.db"], check=True)
    return _demo(a.server_dir, libs)


if __name__ == "__main__":
    sys.exit(main())
