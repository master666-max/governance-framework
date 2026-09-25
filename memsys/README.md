# memsys · 记忆库宿主（v4.3 双包体系的宿主包）

> 定位：v4.3 架构书（`架构书v43-双包体系完整版-20260921.md` §五）的**记忆域宿主**——
> 治理机器（账本/能力/锚/扫描/金标机器）全部来自 `audit-kit`，宿主只做三件事：
> **实现记忆域逻辑、注册领域 kind、注入领域判据。**
> 构建负责方：审计区（用户令 20260921）。
> 依赖：`audit-kit>=1.0`（W0-W3 先行；本仓当前阶段=**框架无关部分先行**——
> prereg 判据/kinds/桥梁，均不 import audit-kit，符合 P9 反向隔离）；
> 演化内核（引擎纯函数）**S1 起移至独立包 `evocore`**（依赖方向：
> `memsys.bridge → {audit-kit, evocore}`）。

## 目录（v4.3 §五对齐 · S1 后）

| 路径 | 内容 | 状态 |
|---|---|---|
| `prereg/金标判据-v1.md` | **金标判据预注册**：irreversible 定义/阈值/ground truth 标法/接管判据（先于实现） | ✅ 已立（v1） |
| `kinds.yml` | 领域 kind 注册：memory_adjudicate / human_override / promotion / attic_nomination | ✅ 已立 |
| `bridge.py` | 引擎事件 → audit-kit 账本桥（MEMSYS_CAP + KINDS；只引 audit-kit 公开面） | ✅ 可运行 |
| `tests/test_bridge.py` | 桥接不变量测试（只走公开面/留痕入账/越权拒/幂等键） | ✅ 全绿 |
| `tests/test_crosscheck.py` | 双包对拍工具不变量测试（隔离违例/files:行号/kind 漂移） | ✅ 全绿 |
| `interface/` | cli.py · mcp_server.py | 🔌 桩（等 audit-kit Ledger/Capability） |

**S1 移出项**：`tunables.py` 与 `engine/{retrieval,lifecycle,decision}.py` → `evocore/`
（对应测试随包搬去 `evocore/tests/`；`evocore` 零依赖，不引 audit-kit 与 memsys）。

**注记（S1 审计实据）**：`bridge.py` 的 sys.path 预置循环含 `"engine"` 子目录项，
有 `os.path.isdir` 守卫——S1 后该目录不存在，此项**自动失效**（死路径、不报错）；
因 bridge 不 import 引擎模块，按 S1"只搬家"纪律**保持字节不动**。
`kinds.yml` 中 actor 模式 `engine|…` 是**账本 actor 角色名**（运行时数据），非模块路径，S1 未改。

## 构建状态（对齐 v4.3 分期 W0-W10）

- 本仓=memsys 侧；**W0-W3（audit-kit 骨架/账本/能力/自举）为前置**，由框架侧负责；
- 当前完成=框架无关部分（上表 ✅）；
- W4 起（引擎基线迁移挂 audit-kit 账本）待框架就位后接线——引擎模块的
  audit-kit 依赖以**接口注入**预留（`LedgerLike` Protocol），不阻塞当前测试。

## 运行

```bash
py -X utf8 -m unittest discover -s tests   # memsys 侧测试（bridge/crosscheck，零依赖）
cd ../evocore/tests && py -X utf8 -m unittest   # 演化内核测试（17+30+9 项）
```
