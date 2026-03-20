-- dm.dm_ar_summary: AR 应收汇总主题表
-- 按公司汇总的应收数据

CREATE TABLE IF NOT EXISTS dm.dm_ar_summary
(
    stat_date Date COMMENT '统计日期',
    company_code String COMMENT '公司编码',
    company_name String COMMENT '公司名称',
    total_ar_amount Decimal(18, 2) COMMENT '应收总额',
    received_amount Decimal(18, 2) COMMENT '已收款总额',
    allocated_amount Decimal(18, 2) COMMENT '已分配总额',
    unallocated_amount Decimal(18, 2) COMMENT '未分配总额',
    overdue_amount Decimal(18, 2) COMMENT '逾期金额',
    overdue_count Int32 COMMENT '逾期单据数',
    total_count Int32 COMMENT '总单据数',
    overdue_rate Decimal(5, 4) COMMENT '逾期率',
    aging_0_30 Decimal(18, 2) COMMENT '0-30天账龄金额',
    aging_31_60 Decimal(18, 2) COMMENT '31-60天账龄金额',
    aging_61_90 Decimal(18, 2) COMMENT '61-90天账龄金额',
    aging_91_180 Decimal(18, 2) COMMENT '91-180天账龄金额',
    aging_180_plus Decimal(18, 2) COMMENT '180天以上账龄金额',
    etl_time DateTime COMMENT 'ETL时间'
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(stat_date)
ORDER BY (stat_date, company_code)
SETTINGS index_granularity = 8192
COMMENT 'AR应收汇总主题表';
