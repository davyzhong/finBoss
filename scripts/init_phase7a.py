"""Phase 7A DDL initialization script"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def init_phase7a() -> None:
    from services.clickhouse_service import ClickHouseDataService
    from clickhouse_driver.errors import Error as ClickHouseError

    ch = ClickHouseDataService()
    DDL_PATH = Path(__file__).parent / "phase7a_ddl.sql"
    if not DDL_PATH.exists():
        raise FileNotFoundError(f"DDL file not found: {DDL_PATH}")

    sql = DDL_PATH.read_text()
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            logger.info(f"  OK {stmt[:60]}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                logger.info(f"  SKIP {stmt[:60]} (already exists)")
            else:
                logger.error(f"  FAIL: {e}")
                raise
        except Exception as e:
            logger.error(f"  FAIL: {e}")
            raise

    logger.info("Phase 7A DDL done.")


if __name__ == "__main__":
    init_phase7a()
