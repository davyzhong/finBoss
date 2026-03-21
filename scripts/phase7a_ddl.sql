-- Phase 7A: Data Quality Reporting Tables
-- dm.quality_reports  — daily quality score per table
-- dm.quality_anomalies — per-field anomaly records linked to a report

CREATE TABLE IF NOT EXISTS dm.quality_reports (
    id              String,
    stat_date       Date,
    table_name      String,
    total_fields    UInt32,
    anomaly_count   UInt32,
    score_pct       Float64,
    generated_at    DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (id, stat_date, table_name);

CREATE TABLE IF NOT EXISTS dm.quality_anomalies (
    id              String,
    report_id       String,
    stat_date       Date,
    table_name      String,
    column_name     String,
    metric          String,
    value           Float64,
    threshold       Float64,
    severity        String,
    status          String DEFAULT 'open',
    detected_at     DateTime,
    resolved_at     DateTime DEFAULT toDateTime('1970-01-01 00:00:00'),
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(detected_at)
ORDER BY (id, stat_date, table_name, column_name, metric);
