-- config/flink/sql/quality.sql
-- Flink SQL: 数据质量检查规则

-- 质控1: bill_no 非空检查
CREATE VIEW quality_check_bill_no AS
SELECT
    bill_no, etl_time,
    CASE WHEN bill_no IS NULL OR bill_no = '' THEN 1 ELSE 0 END as is_null
FROM finboss_iceberg.std.std_ar;

-- 质控2: bill_amount > 0 检查
CREATE VIEW quality_check_amount AS
SELECT
    bill_no, bill_amount, etl_time,
    CASE WHEN bill_amount <= 0 THEN 1 ELSE 0 END as invalid_amount
FROM finboss_iceberg.std.std_ar;

-- 质控3: 数据延迟监控
CREATE VIEW quality_check_timeliness AS
SELECT
    MAX(etl_time) as latest_etl_time,
    CURRENT_TIMESTAMP as check_time,
    TIMESTAMPDIFF(MINUTE, MAX(etl_time), CURRENT_TIMESTAMP) as delay_minutes
FROM finboss_iceberg.std.std_ar;
