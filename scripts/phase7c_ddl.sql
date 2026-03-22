-- Phase 7C: AI 根因分析字段
ALTER TABLE dm.quality_anomalies
ADD COLUMN IF NOT EXISTS root_cause String DEFAULT '';

ALTER TABLE dm.quality_anomalies
ADD COLUMN IF NOT EXISTS analyzed_at DateTime DEFAULT now();

ALTER TABLE dm.quality_anomalies
ADD COLUMN IF NOT EXISTS model_used String DEFAULT '';
