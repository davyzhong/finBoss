#!/usr/bin/env python
"""Initialize Phase 5 related tables and built-in alert rules."""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clickhouse_driver.errors import Error as ClickHouseError

from services.clickhouse_service import ClickHouseDataService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Built-in alert rules
BUILTIN_ALERT_RULES = [
    {
        "id": "rule_overdue_rate",
        "name": "客户逾期率超标",
        "metric": "overdue_rate",
        "operator": "gt",
        "threshold": 0.3,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
        "enabled": 1,
    },
    {
        "id": "rule_overdue_amount",
        "name": "单客户逾期金额超标",
        "metric": "overdue_amount",
        "operator": "gt",
        "threshold": 1000000.0,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
        "enabled": 1,
    },
    {
        "id": "rule_overdue_delta",
        "name": "逾期率周环比恶化",
        "metric": "overdue_rate_delta",
        "operator": "gt",
        "threshold": 0.05,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "中",
        "enabled": 1,
    },
    {
        "id": "rule_new_overdue",
        "name": "新增逾期客户",
        "metric": "new_overdue_count",
        "operator": "gt",
        "threshold": 5.0,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "中",
        "enabled": 1,
    },
    {
        "id": "rule_aging_90",
        "name": "账龄超90天占比高",
        "metric": "aging_90pct",
        "operator": "gt",
        "threshold": 0.2,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
        "enabled": 1,
    },
]


def _insert_rules(ch: ClickHouseDataService) -> None:
    """Insert built-in alert rules."""
    for rule in BUILTIN_ALERT_RULES:
        try:
            ch.execute(
                "INSERT INTO dm.alert_rules "
                "(id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at) "
                "VALUES (%(id)s, %(name)s, %(metric)s, %(operator)s, %(threshold)s, %(scope_type)s, %(scope_value)s, %(alert_level)s, %(enabled)s, now(), now())",
                rule
            )
            logger.info(f"  OK {rule['name']}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                logger.info(f"  SKIP {rule['name']} (already exists)")
            else:
                logger.error(f"  FAIL {rule['name']}: {e}")


def main() -> None:
    ch = ClickHouseDataService()

    ddl_path = Path(__file__).parent / "phase5_ddl.sql"
    if not ddl_path.exists():
        logger.error(f"DDL file not found: {ddl_path}")
        return

    with open(ddl_path) as f:
        ddl_content = f.read()

    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
            logger.info(f"  OK {table_name}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
                logger.info(f"  SKIP {table_name} (already exists)")
            else:
                logger.error(f"  FAIL execute: {e}")
        except Exception as e:
            logger.error(f"  FAIL: {e}")

    # Insert built-in rules
    _insert_rules(ch)

    # Seed management channel recipient from env
    mgmt_channel = os.environ.get("FEISHU_MGMT_CHANNEL_ID", "").strip()
    if mgmt_channel:
        try:
            ch.execute(
                "INSERT INTO dm.report_recipients "
                "(id, recipient_type, name, channel_id, enabled, created_at) "
                "VALUES (%(id)s, %(type)s, %(name)s, %(channel_id)s, %(enabled)s, now())",
                {"id": "mgmt_1", "type": "management", "name": "财务总监群", "channel_id": mgmt_channel, "enabled": 1}
            )
            logger.info("  OK dm.report_recipients (mgmt_1)")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                logger.info("  SKIP dm.report_recipients (mgmt_1 already exists)")
            else:
                logger.error(f"  FAIL dm.report_recipients: {e}")
    else:
        logger.warning("  SKIP dm.report_recipients (FEISHU_MGMT_CHANNEL_ID not set)")

    logger.info("Phase 5 initialization complete!")


if __name__ == "__main__":
    main()
