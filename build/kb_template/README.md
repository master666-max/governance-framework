# 中库模板（kb/ 结构 · 中库规范件 v1 · S3）

> 本目录=**结构模板**：`make_kb.py init|migrate` 会把它与 S2 产物（`build/out/vendored/{gov,evo}`）
> 一起落进目标 `kb/`。结构随模板走；**库内容随用随长**（内容与结构分离）。

```
kb/
├── kb.db                 库数据（SQLite；gov 创建或迁移而来；单写者单机）
├── kb.manifest.json      清单：规范件版本 · gov/evo 版本与 aggregate_sha · 库锚（db sha/events/head/载体）
├── gov/                  治理件（vendored=audit-kit 镜像树 5 件 + gov.manifest.json）
├── evo/                  演化件（evocore 包 + evo.manifest.json）
├── kinds.yml             kind 注册（起步集；开放集，随库生长）
├── prereg/               判据注入位（先于实现的预注册件）
├── index/                导出索引（B 档注入面；可重建，真相在账里）
└── tools/kb.py           运行期 CLI（add/import/query/verify）
```

**两条使用纪律**：
1. **写入口只有 `tools/kb.py`**（构造校验 → gov.append 留痕）——不绕过账本直写；
2. **升级=换 `gov/`|`evo/`**（从新的 S2 产物重新落位），库数据与工具不动；换完跑
   `py -X utf8 audit-kit/conformance.py --kb <kb>` 复查。
