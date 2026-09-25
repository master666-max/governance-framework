# L2-0 服务件（MCP 八工具 · stdio/HTTP）

> 设计依据：`交付-S1v2-20260923/S4设计-L2-0服务件全量落地架构-20260923.md`。
> 定位（L2 设计件 §八/§九）：**运营域级独立服务件**——数据每库独立（`libs/*.db`）、
> 治理实现独立成件（本目录=kernel/+evo/+server.py）、治理位在库外（签发权在人）。
> **本件为装配载荷**（`build/assemble.py` 把它装进服务产物）；从 `build/l2server/` 源位
> 直接运行不可用（核在产物位）——请用**部署位**运行。

## 部署（三步）

```bash
py -X utf8 build/assemble.py all                 # 1) 装配 → build/out/server/（含本件与核）
cp -r build/out/server /opt/l2server             # 2) 拷成运营目录（或就地用 build/out/server）
cd /opt/l2server && py -X utf8 server.py init    # 3) 建库 libs/default.db + 签发运营者 cap
```

## 运行

```bash
py -X utf8 server.py                             # stdio MCP 服务（默认；客户端 spawn 用这个）
py -X utf8 server.py --http :8765                # HTTP 绑定（POST /mcp；SSE 完整合规=设计件 D2）
py -X utf8 server.py stats                       # 调用延迟/失败统计（ops/calls.jsonl 聚合）
py -X utf8 server.py grant --grant-id g2 --actor-prefix llm:other   # 再签一枚 cap（入账）
py -X utf8 server.py selftest                    # 八工具在进程自检（装配器也会跑它）
```

## 真客户端接线（验收"任一平台客户端连上"· 治理位执行）

在本机客户端配置（ZCode 实据位置：`~/.zcode/cli/config.json` 的 `mcp.servers` 段）加入：

```jsonc
"zcode-kb-l2": {
  "command": "py",
  "args": ["-X", "utf8", "<部署目录>/server.py", "--libs-root", "<部署目录>/libs"],
  "env": {}
}
```

重启/重载客户端后即可看到八个工具：
`memory_append / memory_retrieve / memory_promote / memory_tombstone / memory_verify /
anchor / scan / adjudicate`。**期望**：`tools/list` 返回 8 件；`memory_append` 后再
`memory_retrieve` 能取回；`memory_verify` 报链完整。

## 边界与纪律（照设计件）

- **零第三方依赖**（手写 JSON-RPC；MCP SDK 不在环境=实据）；
- **每工具过能力四关**（`DENY:` 前缀可机读）；**caps.json 空表不预填**——签发=ops
  `init`/`grant`（同时写 `capability_issue` 事件入账："权限的历史也在账上"）；
- **单写者**：库被外部写者占（RESERVED 锁）即拒，不硬重试；多客户端=L2-1；
- **输入面六道**：库名白名单 · id/content 长度 · 报文上限（1 MiB）· 目录 roots 圈定 ·
  无动态执行（门⑥）· fail-closed 错误（`REFUSE:`/`FAIL:` 前缀，不回显栈、不崩进程）；
- **延迟观测**：每次工具调用记 `ms`（返回体 `_meta.ms`+`ops/calls.jsonl`）；
- **协议核不调模型**（G8 结构性声明）；adjudicate 的 LLM 挣得=L2-3；
- **未含**（设计件 §七登记）：多 cap 粒度/配额执行/来源审计视图（=L2-2）· HTTP SSE 完整
  合规（D2）· TLS（D8）· 多客户端并发（L2-1）· 跨源冲突（L2-3）。
