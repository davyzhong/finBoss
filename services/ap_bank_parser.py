"""银行对账单解析服务（占位，后续 Task 3 完整实现）"""
import io
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import difflib
from pydantic import BaseModel


def sanitize_filename(name: str) -> str:
    """净化上传文件名：剥离路径、截断 255 字符、仅保留安全字符"""
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)
    return name[:255]


_COLUMN_RULES: list[tuple[str, list[str]]] = [
    ("bank_date", ["交易日期", "记账日期", "日期"]),
    ("counterparty", ["收款人", "对方账户", "对方"]),
    ("amount", ["金额", "付款额"]),
    ("transaction_no", ["流水号", "交易流水", "编号"]),
    ("remark", ["摘要", "用途"]),
]


def _esc(s: str) -> str:
    return s.replace("'", "\\'")


class BankStatementRow(BaseModel):
    bank_date: date
    counterparty: str
    amount: Decimal
    transaction_no: str = ""
    remark: str = ""
    direction: str = "OUT"


class APBankStatementParser:
    """银行对账单 CSV 解析"""

    def __init__(
        self,
        ch: "ClickHouseDataService | None = None",
        payment_term_days: int = 30,
    ):
        from services.clickhouse_service import ClickHouseDataService
        from api.config import get_settings

        self._ch = ch or ClickHouseDataService()
        try:
            settings = get_settings()
            self._payment_term_days = getattr(settings, "ap_default_payment_term_days", payment_term_days)
        except Exception:
            self._payment_term_days = payment_term_days

    def process_upload(
        self, file_content: io.BytesIO, filename: str
    ) -> dict[str, Any]:
        """完整处理流程：解析 → raw 写入 → std 转换 → 返回结果"""
        safe_name = sanitize_filename(filename)

        # Step 1: 解析 CSV
        raw_rows, parse_errors = self._parse_csv(file_content, safe_name)
        if not raw_rows:
            return {
                "file": safe_name,
                "raw_saved": 0,
                "std_saved": 0,
                "parse_errors": len(parse_errors),
                "errors": parse_errors,
            }

        # Step 2: 写入 raw.ap_bank_statement
        raw_saved = self._save_raw(raw_rows, safe_name)

        # Step 3: 转换为 std 并写入
        std_rows = []
        supplier_errors = []
        for row in raw_rows:
            std_row, err = self._transform_to_std(row, safe_name)
            if std_row:
                std_rows.append(std_row)
            if err:
                supplier_errors.append(err)
        std_saved = self._save_std(std_rows)

        return {
            "file": safe_name,
            "raw_saved": raw_saved,
            "std_saved": std_saved,
            "parse_errors": len(parse_errors),
            "supplier_match_errors": len(supplier_errors),
            "errors": parse_errors + supplier_errors,
        }

    # --- CSV 解析 ---
    def _parse_csv(
        self, file_content: io.BytesIO, filename: str
    ) -> tuple[list[dict], list[dict]]:
        import csv

        text = file_content.read().decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        col_map = self._detect_columns(header)

        rows, errors = [], []
        for i, raw_row in enumerate(reader, start=2):
            row_dict = dict(zip(header, raw_row, strict=False))
            row_errors = self._validate_row(row_dict, i, col_map)
            if row_errors:
                errors.extend(row_errors)
                continue  # 跳过有错误的行
            try:
                parsed = self._parse_row(raw_row, header, i, col_map)
                if parsed:  # direction=OUT 才保留
                    rows.append(parsed)
            except Exception as e:
                errors.append({"row": i, "reason": str(e)})
        return rows, errors

    def _detect_columns(self, header: list[str]) -> dict[str, int]:
        """按优先级检测列索引，返回 {field: col_index}"""
        col_map = {}
        for field, keywords in _COLUMN_RULES:
            for idx, col_name in enumerate(header):
                col_lower = col_name.strip()
                for kw in keywords:
                    if kw in col_lower:
                        if field not in col_map:
                            col_map[field] = idx
                        break
        return col_map

    def _validate_row(
        self, row: dict, row_num: int, col_map: dict
    ) -> list[dict]:
        errors = []
        header_list = list(row.keys())
        date_str = ""
        amount_str = ""
        if col_map.get("bank_date", -1) >= 0 and col_map["bank_date"] < len(header_list):
            date_str = row.get(header_list[col_map["bank_date"]], "")
        if col_map.get("amount", -1) >= 0 and col_map["amount"] < len(header_list):
            amount_str = row.get(header_list[col_map["amount"]], "")

        try:
            date.fromisoformat(date_str.strip())
        except Exception:
            errors.append({"row": row_num, "reason": f"无效日期: {date_str}"})
        try:
            Decimal(amount_str.strip().replace(",", ""))
        except (InvalidOperation, ValueError):
            errors.append({"row": row_num, "reason": f"无效金额: {amount_str}"})
        return errors

    def _parse_row(
        self, raw_row: list[str], header: list[str], row_num: int, col_map: dict
    ) -> dict | None:
        """col_map: field_name → column_index"""
        vals = {f: raw_row[i].strip() if i < len(raw_row) else ""
                for f, i in col_map.items()}
        direction = vals.get("direction", "").upper()
        if direction == "IN":
            return None  # 跳过收款行
        amount_str = vals.get("amount", "0").replace(",", "")
        try:
            amt = abs(Decimal(amount_str))
        except InvalidOperation:
            amt = Decimal("0")
        return {
            "bank_date": vals.get("bank_date", ""),
            "counterparty": vals.get("counterparty", ""),
            "amount": str(amt),
            "transaction_no": vals.get("transaction_no", ""),
            "remark": vals.get("remark", ""),
            "direction": "OUT",
        }

    # --- Raw 写入 ---
    def _save_raw(self, rows: list[dict], filename: str) -> int:
        if not rows:
            return 0
        now = datetime.now().isoformat()
        sql = (
            "INSERT INTO raw.ap_bank_statement "
            "(id, file_name, bank_date, transaction_no, counterparty, amount, direction, remark, created_at) VALUES "
        )
        vals = []
        for r in rows:
            vals.append(
                f"('{uuid.uuid4()}', '{_esc(filename)}', "
                f"'{r['bank_date']}', '{_esc(r['transaction_no'])}', "
                f"'{_esc(r['counterparty'])}', {r['amount']}, "
                f"'{r['direction']}', '{_esc(r['remark'])}', '{now}')"
            )
        self._ch.execute(sql + ", ".join(vals))
        return len(rows)

    # --- STD 转换 ---
    def _transform_to_std(
        self, raw_row: dict, filename: str
    ) -> tuple[dict | None, dict | None]:
        bank_date = date.fromisoformat(raw_row["bank_date"])
        due_date = bank_date + timedelta(days=self._payment_term_days)
        supplier_name = raw_row["counterparty"]
        matched_name = self._match_supplier(supplier_name)
        return {
            "bank_date": bank_date.isoformat(),
            "due_date": due_date.isoformat(),
            "supplier_name": matched_name,
            "amount": raw_row["amount"],
            "bank_transaction_no": raw_row["transaction_no"],
            "source_file": filename,
        }, None

    def _match_supplier(self, name: str) -> str:
        """供应商匹配：精确 → 去括号精确 → 模糊 → 返回原名"""
        known = self._get_known_suppliers()
        if name in known:
            return name
        # 去括号匹配
        name_no_brackets = re.sub(r"[（(].*?[）)]", "", name).strip()
        if name_no_brackets in known:
            return name_no_brackets
        # 模糊匹配
        best_match, best_score = name, 0.0
        for supplier in known:
            score = difflib.SequenceMatcher(None, name_no_brackets, supplier).ratio()
            if score > best_score:
                best_score = score
                best_match = supplier
        if best_score >= 0.85:
            return best_match
        return name  # 未匹配，返回原名，code 留空

    def _get_known_suppliers(self) -> list[str]:
        try:
            rows = self._ch.execute_query(
                "SELECT DISTINCT supplier_name FROM std.ap_std_record WHERE supplier_name != ''"
            )
            return [r.get("supplier_name", "") for r in rows if r.get("supplier_name")]
        except Exception:
            return []

    # --- STD 写入 ---
    def _save_std(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        now = datetime.now().isoformat()
        sql = (
            "INSERT INTO std.ap_std_record "
            "(id, supplier_code, supplier_name, bank_date, due_date, amount, "
            "received_amount, is_settled, bank_transaction_no, payment_method, source_file, etl_time) "
            "VALUES "
        )
        vals = []
        for r in rows:
            vals.append(
                f"('{uuid.uuid4()}', '', "  # supplier_code 空，暂未建供应商表
                f"'{_esc(r['supplier_name'])}', "
                f"'{r['bank_date']}', '{r['due_date']}', {r['amount']}, "
                f"0, 0, '{_esc(r['bank_transaction_no'])}', '', "
                f"'{_esc(r['source_file'])}', '{now}')"
            )
        self._ch.execute(sql + ", ".join(vals))
        return len(rows)

