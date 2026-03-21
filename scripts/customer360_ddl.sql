-- scripts/customer360_ddl.sql
-- Phase 4B 客户360相关表的 DDL
-- 执行方式: clickhouse-client --queries-file=scripts/customer360_ddl.sql
-- ClickHouse 23.x: PRIMARY KEY 必须是 ORDER BY 的前缀；ORDER BY 本身已定义排序键

-- raw_customer: 标准化客户原始记录（ReplacingMergeTree，同主键去重）
CREATE TABLE IF NOT EXISTS raw.raw_customer (
    id                      String,
    source_system           String,
    customer_id            String,
    customer_name          String,
    customer_short_name    String,
    tax_id                 String,
    credit_code            String,
    address                String,
    contact                String,
    phone                  String,
    etl_time              DateTime
) ENGINE = ReplacingMergeTree(etl_time)
ORDER BY (source_system, customer_id);

-- dm_customer360: 客户360事实表（ReplacingMergeTree，每日快照覆盖更新）
CREATE TABLE IF NOT EXISTS dm.dm_customer360 (
    unified_customer_code   String,
    raw_customer_ids       Array(String),
    source_systems         Array(String),
    customer_name          String,
    customer_short_name    String,
    ar_total               Decimal(18, 2),
    ar_overdue            Decimal(18, 2),
    overdue_rate           Float32,
    payment_score          Float32,
    risk_level             String,
    merge_status           String,
    last_payment_date      Date,
    first_coop_date       Date,
    company_code           String,
    stat_date              Date,
    updated_at             DateTime
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (unified_customer_code, stat_date);

-- customer_merge_queue: 合并复核队列
CREATE TABLE IF NOT EXISTS dm.customer_merge_queue (
    id                      String,
    action                  String,
    similarity              Float32,
    reason                  String,
    customer_ids            Array(String),
    customer_names          Array(String),
    unified_customer_code   String,
    status                 String,
    operator               String,
    operated_at             DateTime,
    undo_record_id         String,
    created_at             DateTime
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (id, created_at);

-- merge_history: 合并历史（可逆操作记录）
CREATE TABLE IF NOT EXISTS dm.merge_history (
    id                      String,
    unified_customer_code   String,
    source_system           String,
    original_customer_id    String,
    operated_at             DateTime,
    operator                String,
    undo_record_id          String
) ENGINE = ReplacingMergeTree(operated_at)
ORDER BY (id, operated_at);
