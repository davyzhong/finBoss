-- scripts/phase6_ddl.sql
-- Phase 6 DDL: 业务员映射表 + AP 银行对账单表

-- raw.ap_bank_statement: 原始银行对账单
CREATE TABLE IF NOT EXISTS raw.ap_bank_statement (
    id              String,
    file_name       String,
    bank_date       Date,
    transaction_no  String,
    counterparty    String,
    amount          Decimal(18, 2),
    direction       String,
    remark          String,
    created_at      DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (file_name, bank_date, transaction_no)
SETTINGS allow_experimental_object_type = 1;

-- std.ap_std_record: 标准化 AP 记录
CREATE TABLE IF NOT EXISTS std.ap_std_record (
    id                  String,
    supplier_code       String,
    supplier_name       String,
    bank_date           Date,
    due_date            Date,
    amount              Decimal(18, 2),
    received_amount     Decimal(18, 2),
    is_settled          UInt8,
    settlement_date     Date,
    bank_transaction_no String,
    payment_method      String,
    source_file         String,
    etl_time            DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(etl_time)
ORDER BY (bank_transaction_no)
SETTINGS allow_experimental_object_type = 1;

-- dm.salesperson_mapping: 业务员主表
CREATE TABLE IF NOT EXISTS dm.salesperson_mapping (
    id               String,
    salesperson_id   String,
    salesperson_name String,
    feishu_open_id  String,
    enabled          UInt8,
    created_at       DateTime,
    updated_at       DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (salesperson_id, updated_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.salesperson_customer_mapping: 客户→业务员多对多映射
CREATE TABLE IF NOT EXISTS dm.salesperson_customer_mapping (
    id              String,
    salesperson_id  String,
    customer_id     String,
    customer_name   String,
    created_at      DateTime,
    UNIQUE (salesperson_id, customer_id)
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (salesperson_id, customer_id)
SETTINGS allow_experimental_object_type = 1;

-- 扩展 dm.report_records 以支持 Phase 6 报告类型
ALTER TABLE dm.report_records
    ADD COLUMN IF NOT EXISTS salesperson_id String DEFAULT '',
    ADD COLUMN IF NOT EXISTS supplier_code String DEFAULT '';
