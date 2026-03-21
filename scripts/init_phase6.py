#!/usr/bin/env python
"""初始化 Phase 6 相关表"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    from services.clickhouse_service import ClickHouseDataService
    from clickhouse_driver.errors import Error as ClickHouseError

    ch = ClickHouseDataService()
    ddl_path = Path(__file__).parent / "phase6_ddl.sql"
    if not ddl_path.exists():
        logger.error(f"DDL 文件不存在: {ddl_path}")
        return

    with open(ddl_path) as f:
        ddl_content = f.read()

    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            # 提取表名
            if "CREATE TABLE" in stmt.upper():
                table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
                logger.info(f"  OK {table_name}")
            elif "ALTER TABLE" in stmt.upper():
                logger.info(f"  OK dm.report_records (ALTER)")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
                logger.info(f"  SKIP {table_name} (already exists)")
            else:
                logger.error(f"  FAIL execute: {e}")
        except Exception as e:
            logger.error(f"  FAIL: {e}")

    logger.info("Phase 6 初始化完成！")


if __name__ == "__main__":
    main()
