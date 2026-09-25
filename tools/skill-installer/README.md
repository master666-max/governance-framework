# skill-installer README（G-03 原型 v0，20260919）

## 装（一条命令）
```
sh install.sh <目标目录>
```
生成 MVP 六件：账本（九列 schema）/supersede 侧表/事故表/审计表/锚点协议/
EXCL 模板/预注册 SOP v1.2 模板。装完自动跑五项自检。

## 自检五项
账本 schema / 侧表族 / 锚点协议 / EXCL 模板 / SOP 条款⑤——任一 FAIL 即 exit 1。

## 可选件（不在 v0 范围，按需向审计区领取或照 tools/ 自装）
- 治理仪器四件：pre-commit 钩子（R2 闸门+SOP 副本一致）/invariant_scanner
  v1.1（R1 死字段+R2 恒真，`--r2-only` 供钩子消费）/constants-registry
  常数簿/findings-ledger 处置台账；
- L5 提炼层：scan2b→materialize2→双盲双提→merge2→append2 九圈管线
  （DELTA-REPORT#9 §七 命令全集）；
- 安装前置自判：说明书 v2 §0.1 裁判树+§0.2 break-even。

## v0 已知限制（如实）
1. 骨架生成器：只造空模板，不含本案 10,677 条存量迁移工具；
2. 圈号参数化未做（管线脚本仍带圈号专名）；
3. 许可隔离声明模板未含（G-02，S4 发布清单）；
4. SOP 模板为骨架——各领域判据/门值须自行填充（带表体系需先跑评测校准）。
