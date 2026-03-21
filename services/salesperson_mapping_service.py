"""业务员映射服务"""
import csv
import io
import re
import uuid
from datetime import datetime
from typing import Any

from services.clickhouse_service import ClickHouseDataService

_SALESperson_ID_RE = re.compile(r"^[A-Z0-9]+$")


def escape_ch_string(s: str) -> str:
    """转义 ClickHouse 字符串中的单引号"""
    return s.replace("'", "\\'")


class SalespersonMappingService:
    """业务员映射 CRUD + CSV 上传"""

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()

    # --- Active salesperson list ---
    def list_active(self) -> list[dict[str, Any]]:
        rows = self._ch.execute_query(
            "SELECT id, salesperson_id, salesperson_name, feishu_open_id "
            "FROM dm.salesperson_mapping WHERE enabled = 1"
        )
        return rows

    # --- Mapping CRUD ---
    def list_mappings(self) -> list[dict[str, Any]]:
        return self._ch.execute_query(
            "SELECT * FROM dm.salesperson_mapping ORDER BY created_at DESC"
        )

    def create_mapping(self, data: dict) -> dict:
        sid = data["salesperson_id"]
        self._validate_salesperson_id(sid)
        now = datetime.now().isoformat()
        record_id = str(uuid.uuid4())
        sql = (
            f"INSERT INTO dm.salesperson_mapping "
            f"(id, salesperson_id, salesperson_name, feishu_open_id, enabled, created_at, updated_at) "
            f"VALUES ('{record_id}', '{sid}', '{escape_ch_string(data['salesperson_name'])}', "
            f"'{escape_ch_string(data.get('feishu_open_id') or '')}', "
            f"{int(data.get('enabled', True))}, '{now}', '{now}')"
        )
        self._ch.execute(sql)
        return {"id": record_id, **data}

    def update_mapping(self, record_id: str, data: dict) -> dict | None:
        rows = self._ch.execute_query(
            f"SELECT 1 FROM dm.salesperson_mapping WHERE id = '{record_id}'"
        )
        if not rows:
            return None
        if "salesperson_id" in data:
            self._validate_salesperson_id(data["salesperson_id"])
        now = datetime.now().isoformat()
        sets = [f"updated_at = '{now}'"]
        for k, v in data.items():
            if k in ("salesperson_id", "salesperson_name"):
                sets.append(f"{k} = '{escape_ch_string(str(v))}'")
            elif k == "feishu_open_id":
                sets.append(f"feishu_open_id = '{escape_ch_string(v or '')}'")
            elif k == "enabled":
                sets.append(f"enabled = {int(v)}")
        self._ch.execute(
            f"ALTER TABLE dm.salesperson_mapping UPDATE {', '.join(sets)} WHERE id = '{record_id}'"
        )
        return {"id": record_id, **data}

    def delete_mapping(self, record_id: str) -> bool:
        try:
            self._ch.execute(
                f"ALTER TABLE dm.salesperson_mapping DELETE WHERE id = '{record_id}'"
            )
            return True
        except Exception:
            return False

    # --- Customer mapping ---
    def list_customers_by_salesperson(self, salesperson_id: str) -> list[dict]:
        return self._ch.execute_query(
            f"SELECT customer_id, customer_name FROM dm.salesperson_customer_mapping "
            f"WHERE salesperson_id = '{salesperson_id}'"
        )

    def upsert_customer_mapping(
        self,
        salesperson_id: str,
        customer_id: str,
        customer_name: str,
    ) -> None:
        record_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        sql = (
            f"INSERT INTO dm.salesperson_customer_mapping "
            f"(id, salesperson_id, customer_id, customer_name, created_at) "
            f"VALUES ('{record_id}', '{salesperson_id}', '{escape_ch_string(customer_id)}', "
            f"'{escape_ch_string(customer_name)}', '{now}')"
        )
        self._ch.execute(sql)

    # --- CSV upload ---
    def _parse_csv_upload(
        self, file_content: io.BytesIO, filename: str
    ) -> tuple[list[dict], list[dict]]:
        """解析 CSV，返回 (rows, errors)"""
        text = file_content.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows, errors = [], []
        for i, raw in enumerate(reader, start=2):  # start=2: header is row 1
            sid = raw.get("salesperson_id", "").strip()
            try:
                self._validate_salesperson_id(sid)
            except ValueError as e:
                errors.append({"row": i, "reason": str(e)})
                continue
            rows.append({
                "salesperson_id": sid,
                "salesperson_name": raw.get("salesperson_name", "").strip(),
                "feishu_open_id": raw.get("feishu_open_id", "").strip(),
                "customer_id": raw.get("customer_id", "").strip(),
                "customer_name": raw.get("customer_name", "").strip(),
            })
        return rows, errors

    def upload_csv(self, file_content: io.BytesIO, filename: str) -> dict:
        rows, errors = self._parse_csv_upload(file_content, filename)
        imported, skipped = 0, 0
        for row in rows:
            # Upsert salesperson
            existing = self._ch.execute_query(
                f"SELECT id FROM dm.salesperson_mapping WHERE salesperson_id = '{row['salesperson_id']}' LIMIT 1"
            )
            if existing:
                self.update_mapping(existing[0]["id"], {
                    "salesperson_name": row["salesperson_name"],
                    "feishu_open_id": row["feishu_open_id"],
                    "enabled": True,
                })
            else:
                self.create_mapping({
                    "salesperson_id": row["salesperson_id"],
                    "salesperson_name": row["salesperson_name"],
                    "feishu_open_id": row["feishu_open_id"],
                    "enabled": True,
                })
            # Upsert customer mapping
            if row["customer_id"]:
                try:
                    self.upsert_customer_mapping(
                        row["salesperson_id"],
                        row["customer_id"],
                        row["customer_name"],
                    )
                    imported += 1
                except Exception:
                    skipped += 1
        return {
            "imported": imported,
            "skipped": skipped,
            "parse_errors": len(errors),
            "errors": errors,
        }

    def _validate_salesperson_id(self, sid: str) -> str:
        if not _SALESperson_ID_RE.match(sid):
            raise ValueError(
                f"Invalid salesperson_id '{sid}': must be uppercase alphanumeric only"
            )
        return sid
