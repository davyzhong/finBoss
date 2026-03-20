-- dm.dm_customer_ar: 客户应收主题表
-- 按客户维度的应收数据

CREATE TABLE IF NOT EXISTS dm.dm_customer_ar
(
    stat_date Date COMMENT '统计日期',
    customer_code String COMMENT '客户编码',
    customer_name String COMMENT '客户名称',
    company_code String COMMENT '公司编码',
    total_ar_amount Decimal(18, 2) COMMENT '应收总额',
    overdue_amount Decimal(18, 2) COMMENT '逾期金额',
    overdue_count Int32 COMMENT '逾期单据数',
    total_count Int32 COMMENT '总单据数',
    overdue_rate Decimal(5, 4) COMMENT '逾期率',
    last_bill_date Date COMMENT '最近单据日期',
    etl_time DateTime COMMENT 'ETL时间'
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(stat_date)
ORDER BY (stat_date, company_code, customer_code)
SETTINGS index_granularity = 8192
COMMENT '客户应收主题表';
