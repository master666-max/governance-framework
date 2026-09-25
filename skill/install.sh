#!/bin/sh
# install.sh — 自演化知识库构建体系 · MVP 六件安装器 v0（G-03 原型，20260919）
# 用法: sh install.sh <目标目录>
# 装什么: MVP 六件（账本/锚点协议/supersede 侧表/EXCL 清单/预注册SOP v1.2 模板/豁免清单条款）
# 不装什么: 治理仪器四件与 L5 提炼层（可选件，见 README §可选件；break-even 见说明书 v2 §0.2）
set -e
DST="${1:?用法: sh install.sh <目标目录>}"
[ -d "$DST" ] || { echo "目标目录不存在: $DST"; exit 1; }
cd "$DST"

echo "[1/4] 生成账本（claim_ledger.csv 九列 schema）"
printf 'claim_id,source_file,location_anchor,claim_type,verbatim_quote,experiment_id,source_type,status,superseded_by\n' > claim_ledger.csv

echo "[2/4] 生成侧表族（supersede/incident/audit）"
printf 'old_claim_id,new_claim_id,reason,ts\n' > supersede_log.csv
printf '实验ID,事故描述摘录,涉及机制,死因分类\n' > incident-log.csv
printf 'ts,actor,action,object,result\n' > audit-log.csv

echo "[3/4] 生成锚点协议与 EXCL 清单模板"
cat > ANCHOR-PROTOCOL.md <<'EOF'
# 锚点协议 v1（安装即生效）
1. 一切断言必带 file@commit:line + ≤200 字逐字摘录（不是转述）。
2. 哈希必须声明基准态（blob 态 / 工作树态——core.autocrlf=true 时两者不等）。
3. 计数必须声明基准三元组：匹配模式 / 路径域（同名件多 blob 时用 blob 或全路径）/ 命中类型。
4. 验证判定绑定作用域 blob；判定不自动传递到同名其他 blob。
5. 覆盖边界外不称"不存在"；缺失不配机制解释；证据不足处不配严重度。
EOF
cat > EXCL-清单模板.txt <<'EOF'
# 增量制图排除清单（起步模板——按本领域增删；逐模式排除计数须产出）
# 下发单 / 审计区下发副本 / 通报单 / 知会单 / 补正单 / 更正要求单 / 澄清件 /
# 材料包副本 / 预注册SOP副本 / 反向输出包 / commit统一提醒 / __pycache__ / .zip .7z .pyc .log
EOF

echo "[4/4] 生成预注册 SOP v1.2 模板（五条款+措施 ABC+三要素）"
cat > 预注册SOP-模板-v1.2.md <<'EOF'
# 预注册 SOP v1.2 模板（缺一不受理）
条款① 门值引带：判定门值必须引用带表文件@锚点（评测三口径：混合带判定唯一，
线内分布不构成第二判定门；分类数据引带须带亚族名——三要素缺一按引用不成立）。
条款② 判据-实现映射：每个判据注明实现位置；机制口径注记前置。
条款③ 未命中分支预注册：方向性假设未命中即刻转因子发现（E96 范式），单点赌注禁止。
条款④ 自测门：判据带浮点容差（≥1e-9）；锚必须绑定代码组装输出（P-024），
不得只锚手算式；负测试必配。
条款⑤ 逐位一致宣称强制附豁免清单（包装分隔行/CRLF/计时列/已知仪器差），
无豁免注记的宣称按可机械否证处理。
措施A 计数声明基准（模式/路径域/命中类型）；措施B 判定作用域绑 blob；
措施C 同名件 blob 对账+canonical 声明。
EOF

echo "== 安装自检（五项，全部 PASS 才算装好）=="
ok=0
grep -q "^claim_id," claim_ledger.csv && echo "自检1 账本schema PASS" && ok=$((ok+1))
[ -f supersede_log.csv ] && [ -f incident-log.csv ] && echo "自检2 侧表族 PASS" && ok=$((ok+1))
[ -f ANCHOR-PROTOCOL.md ] && echo "自检3 锚点协议 PASS" && ok=$((ok+1))
[ -f EXCL-清单模板.txt ] && echo "自检4 EXCL模板 PASS" && ok=$((ok+1))
grep -q "条款⑤" 预注册SOP-模板-v1.2.md && echo "自检5 SOP模板 PASS" && ok=$((ok+1))
[ "$ok" = "5" ] && echo "== 安装完成 5/5 ==" || { echo "== 自检失败 $ok/5 =="; exit 1; }
echo "下一步: 读 ANCHOR-PROTOCOL.md 通读纪律；EXCL 按领域增删；说明书 v2 §第三章 开始第一波。"
