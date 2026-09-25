-- audit-kit ledger schema（v4.3 §六；UTF-8）
CREATE TABLE IF NOT EXISTS events (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         DATETIME DEFAULT CURRENT_TIMESTAMP,
  actor      TEXT NOT NULL,
  kind       TEXT NOT NULL,
  payload    JSON NOT NULL,
  prev_hash  TEXT NOT NULL,
  self_hash  TEXT NOT NULL
);

-- append-only 物理强制（P3）：UPDATE/DELETE 一律 ABORT
CREATE TRIGGER IF NOT EXISTS no_update
BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'append-only: events 表禁止 UPDATE'); END;

CREATE TRIGGER IF NOT EXISTS no_delete
BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'append-only: events 表禁止 DELETE'); END;

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);

-- 事件哈希算法版本闸（W2-N2 · 20260923 开工批）：算法版本入库登记，开库即验。
-- 病灶：hashes.py 的 event_hash 于 20260923 评审升 v2（actor/kind 并入哈希输入），
-- 而此前写入的库仍为 v1 值 ⇒ verify() 报「哈希不符 seq=1（疑似篡改）」——把
-- 算法换代误报成篡改，且无版本闸可区分。与融合形态 evo_seat.py §2 同族同语义。
CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (k, v) VALUES ('hash_algo', 'v2');
