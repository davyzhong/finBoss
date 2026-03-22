"""Phase 7C DDL 初始化脚本"""
import logging
from pathlib import Path

from clickhouse_driver.errors import Error as ClickHouseError

from services.clickhouse_service import ClickHouseDataService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
DDL_FILE = SCRIPT_DIR / "phase7c_ddl.sql"


def init_phase7c() -> None:
    if not DDL_FILE.exists():
        raise FileNotFoundError(f"DDL file not found: {DDL_FILE}")

    ch = ClickHouseDataService()
    statements = [s.strip() for s in DDL_FILE.read_text(encoding="utf-8").split(";") if s.strip()]

    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            logger.info(f"OK: {stmt[:60]}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 44:
                logger.info(f"SKIP (already exists): {stmt[:60]}")
            else:
                logger.error(f"FAIL: {stmt[:60]} — {e}")
                raise

    logger.info("Phase 7C DDL done.")


if __name__ == "__main__":
    init_phase7c()
