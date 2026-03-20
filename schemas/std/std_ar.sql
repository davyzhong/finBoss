-- std.std_ar: 标准化应收单据表
-- 存储来自 ERP 的标准化 AR 数据

CREATE TABLE IF NOT EXISTS std.std_ar
(
    id String COMMENT '主键ID',
    stat_date Date COMMENT '统计日期',
    company_code String COMMENT '公司编码',
    company_name String COMMENT '公司名称',
    customer_code String COMMENT '客户编码',
    customer_name String COMMENT '客户名称',
    bill_no String COMMENT '应收单号',
    bill_date Date COMMENT '单据日期',
    due_date Date COMMENT '到期日期',
    bill_amount Decimal(18, 2) COMMENT '单据金额',
    received_amount Decimal(18, 2) COMMENT '已收款金额',
    allocated_amount Decimal(18, 2) COMMENT '已分配金额',
    unallocated_amount Decimal(18, 2) COMMENT '未分配金额',
    aging_bucket String COMMENT '账龄区间',
    aging_days Int32 COMMENT '账龄天数',
    is_overdue Bool COMMENT '是否逾期',
    overdue_days Int32 COMMENT '逾期天数',
    status String COMMENT '状态',
    etl_time DateTime COMMENT 'ETL时间'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(stat_date)
ORDER BY (stat_date, company_code, customer_code, bill_no)
SETTINGS index_granularity = 8192
COMMENT '标准化应收单据表';
