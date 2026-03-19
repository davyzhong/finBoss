-- config/flink/sql/std_ar.sql
-- Flink SQL: 将 raw_kingdee.ar_verify 转换为 std_ar 标准层

CREATE CATALOG finboss_iceberg WITH (
    'type' = 'iceberg',
    'catalog-impl' = 'org.apache.iceberg.rest.RESTCatalog',
    'uri' = '${env.NESSIE_URI:-http://nessie:19120}',
    'warehouse' = 's3://finboss/warehouse',
    's3.endpoint' = 'http://minio:9000',
    's3.access-key' = 'minioadmin',
    's3.secret-key' = 'minioadmin'
);

USE CATALOG finboss_iceberg;

-- 创建 raw 层视图
CREATE VIEW IF NOT EXISTS raw_ar_view AS
SELECT
    fid, fbillno, fdate, fcustid, fcustname,
    fbillamount, fpaymentamount, fallocateamount, funallocateamount,
    fstatus, fcompanyid, fdocumentstatus, CURRENT_TIMESTAMP() as etl_time
FROM raw_kingdee.ar_verify;

-- 创建 std_ar 表
CREATE TABLE IF NOT EXISTS std_ar (
    id STRING,
    stat_date TIMESTAMP,
    company_code STRING,
    company_name STRING,
    customer_code STRING,
    customer_name STRING,
    bill_no STRING,
    bill_date TIMESTAMP,
    due_date TIMESTAMP,
    bill_amount DECIMAL(18, 2),
    received_amount DECIMAL(18, 2),
    allocated_amount DECIMAL(18, 2),
    unallocated_amount DECIMAL(18, 2),
    currency STRING DEFAULT 'CNY',
    exchange_rate DECIMAL(10, 4) DEFAULT 1.0,
    bill_amount_base DECIMAL(18, 2),
    received_amount_base DECIMAL(18, 2),
    aging_bucket STRING,
    aging_days INT,
    is_overdue BOOLEAN,
    overdue_days INT DEFAULT 0,
    status STRING,
    document_status STRING,
    employee_name STRING,
    dept_name STRING,
    etl_time TIMESTAMP,
    PRIMARY KEY (id) NOT ENFORCED
) WITH ('format' = 'parquet');

-- 插入标准化数据
INSERT INTO std_ar
SELECT
    MD5(CONCAT(CAST(fid AS STRING), fbillno)) as id,
    CURRENT_TIMESTAMP as stat_date,
    CAST(fcompanyid AS STRING) as company_code,
    '公司' || CAST(fcompanyid AS STRING) as company_name,
    CAST(fcustid AS STRING) as customer_code,
    fcustname as customer_name,
    fbillno as bill_no,
    fdate as bill_date,
    TIMESTAMPADD(DAY, 30, fdate) as due_date,
    fbillamount as bill_amount,
    fpaymentamount as received_amount,
    fallocateamount as allocated_amount,
    funallocateamount as unallocated_amount,
    fbillamount as bill_amount_base,
    fpaymentamount as received_amount_base,
    CASE
        WHEN DAYS(CURRENT_DATE, fdate) <= 30 THEN '0-30'
        WHEN DAYS(CURRENT_DATE, fdate) <= 60 THEN '31-60'
        WHEN DAYS(CURRENT_DATE, fdate) <= 90 THEN '61-90'
        WHEN DAYS(CURRENT_DATE, fdate) <= 180 THEN '91-180'
        ELSE '180+'
    END as aging_bucket,
    DAYS(CURRENT_DATE, fdate) as aging_days,
    CASE WHEN DAYS(CURRENT_DATE, fdate) > 30 THEN TRUE ELSE FALSE END as is_overdue,
    GREATEST(DAYS(CURRENT_DATE, fdate) - 30, 0) as overdue_days,
    fstatus as status,
    fdocumentstatus as document_status,
    NULL as employee_name,
    NULL as dept_name,
    etl_time
FROM raw_ar_view;
