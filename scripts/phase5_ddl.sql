-- Phase 5 DDL: 逾期预警引擎 + 自动化报告相关表

-- dm.alert_rules
CREATE TABLE IF NOT EXISTS dm.alert_rules (
    id             String,
    name           String,
    metric         String,
    operator       String,
    threshold      Float64,
    scope_type     String,
    scope_value    String,
    alert_level    String,
    enabled        UInt8,
    created_at     DateTime,
    updated_at     DateTime
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (id, updated_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.alert_history
CREATE TABLE IF NOT EXISTS dm.alert_history (
    id             String,
    rule_id        String,
    rule_name      String,
    alert_level    String,
    metric         String,
    operator       String,
    metric_value   Float64,
    threshold      Float64,
    scope_type     String,
    scope_value    String,
    triggered_at   DateTime,
    sent           UInt8
) ENGINE = ReplacingMergeTree(triggered_at)
ORDER BY (rule_id, triggered_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.report_records
CREATE TABLE IF NOT EXISTS dm.report_records (
    id             String,
    report_type    String,
    period_start   Date,
    period_end     Date,
    recipients     String,
    file_path      String,
    sent_at        DateTime,
    status         String
) ENGINE = ReplacingMergeTree(sent_at)
ORDER BY (report_type, sent_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.report_recipients
CREATE TABLE IF NOT EXISTS dm.report_recipients (
    id              String,
    recipient_type  String,
    name            String,
    channel_id      String,
    enabled         UInt8,
    created_at      DateTime
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (recipient_type, id)
SETTINGS allow_experimental_object_type = 1;
