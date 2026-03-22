-- Phase 7B DDL: Add assignee, sla_hours columns to dm.quality_anomalies
ALTER TABLE dm.quality_anomalies
  ADD COLUMN IF NOT EXISTS assignee String DEFAULT '';

ALTER TABLE dm.quality_anomalies
  ADD COLUMN IF NOT EXISTS sla_hours Float64 DEFAULT 0;
