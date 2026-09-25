# build/ · S2 四包装配器（一码四包）

> 设计依据：`交付-S1v2-20260923/S2设计v2-四包装配器全量落地架构-20260923.md`
> （总工单对齐版；v1 留档 `S2设计-四包装配器落地架构-20260923.md`）。
> **一码**=三棵权威源树（`audit-kit/{core,ledger}` · `evocore/` · `evo-seat/evo_seat.py`）；
> **四产物**=代码文件**逐字节副本** + 生成件（清单/壳/pyproject/skeleton）；**零文本改写**。

## 用法

```bash
py -X utf8 build/assemble.py all                    # 装配四产物 → 逐产物 conformance → 写清单
py -X utf8 build/assemble.py reconcile              # 对账五查（产物==清单 · 副本==源 · 重跑 · 登记件 · evo 冒烟）
py -X utf8 build/assemble.py audit                  # S2-T3/T4/T5/T7/T8 验收报告（只读）
py -X utf8 build/assemble.py check-copy <副本路径> --kind fused|gov|evo   # 外部副本两级对账
py -X utf8 build/tests/test_assemble.py             # 不变量测试（双跑逐位/篡改三式/一致性/段哈希）
```

## 目录

```
build/
├── assemble.py                  装配器（唯一脚本；stdlib；确定性）
├── README.md                    本件
├── manifests/                   【登记件·committed】五份 *.manifest.json（对账锚）
└── out/                         【产物·gitignored·可重建】
    ├── fused/     evo_seat.py · framework_segment.txt · fused.manifest.json
    ├── vendored/  gov/{core×3,ledger×2,manifest} · evo/{evocore×5,manifest}
    ├── pypkg/     audit-kit/{auditkit/{__init__, _payload×5},pyproject,README} · evocore/{evocore×5,tests×4,README,pyproject} · manifest
    └── server/    kernel/{core×3,ledger×2} · evo/evocore×5 · caps/quotas.skeleton.json · libs/ · ops/conformance.sh · manifest
```

## 清单 schema（登记件）

```json
{"form","versions":{组件:版本},"spec","schema_version","surface"(治理载荷件),
 "files":{产物相对路径:sha256},"sources":{产物文件:源路径},"aggregate_sha",
 "conformance":[{"what","target","exit","passed","total"}],
 "segment":{file,sha256,chars,bytes}(仅 fused)}
```
- `sources` 映射使**外部审计者不依赖装配器**即可复核对账（逐条 sha256）；
- 确定性口径：cmd 路径记 `<out>` 占位（禁绝对路径）；无时间戳；utf-8/LF ⇒ **双跑逐位一致**。

## 验收读数（2026-09-23 实跑 · 复验命令见交付验收报告）

| 项 | 读数 |
|---|---|
| 装配（T7 观测位） | **4/4 产物过 conformance · 约 2.3 s**（触发器：>60 s 才优化） |
| conformance | fused **14/14** · gov/pypkg-payload/server-kernel 各 **9/9** |
| 对账五查 | **PASS** |
| 跨产物一致性（T5） | 源 16 个 · 副本 **36** 份 · **违例 0** |
| 复用记账（T8） | 产物 **50** = 副本 **36** + 派生 **1** + 生成 **13**（生成=清单 5+壳/pyproject/README/skeleton/ops/.gitkeep；**零逻辑**） |
| 产物安全面（T3） | 产物 .py **33 件 · 0 未豁免**（门⑥；带 `--allow gov_types,hashes,capabilities,ledger,evocore`） |
| 产物坏味面（T4） | 生成件（壳）**0 候选**；副本读数==源（由字节相等推出——**勿跨副本合并扫描**，会产生假重复块） |
| 副本对账真例 | blender 副本：冻结面 **PASS**（`622110a5af2cc4d7`）+ 适配面 `§7×2/§9×2` |
| 不变量测试 | `build/tests/test_assemble.py` **8 项**（双跑逐位/副本==源/一致性/段哈希/篡改三式/check-copy ±） |

## 边界（如实声明）

- **产物体**：`out/` 全部可弃可重建；一切身份在清单（`manifests/` 才是登记锚）；
- **门调用姿势**：产物载荷以平铺模块名互相导入 ⇒ 门④ 需 `--allow` 表显式声明（仓内惯例同款）；
- **不修源**（除 T2 清源）：装配期不改任何源字节；产物=源的**逐字节**副本；
- **未覆盖**（设计件 §七登记）：D2 pip 顶层模块名相撞 / D3 pip install 未实测 / D6 ops 脚本依赖仓内工具路径；
- **冻结件**：`evo-seat` 的 7 个魔法数登记于 D1（改动=破 framework_sha 基线，随内核版本周期处理）。
