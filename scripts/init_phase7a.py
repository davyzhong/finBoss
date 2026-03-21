"""Phase 7A DDL initialization script"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.clickhouse_service import ClickHouseDataService

DDL_PATH = Path(__file__).parent / "phase7a_ddl.sql"


def init_phase7a() -> None:
    ch = ClickHouseDataService()
    sql = DDL_PATH.read_text()
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            print(f"OK: {stmt[:60]}")
        except Exception as e:
            if "already exists" in str(e).lower() or "code: 57" in str(e):
                print(f"SKIP (exists): {stmt[:60]}")
            else:
                raise
    print("Phase 7A DDL done.")


if __name__ == "__main__":
    init_phase7a()
