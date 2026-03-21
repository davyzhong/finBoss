"""测试 Phase 6 DDL 和初始化脚本"""
import pytest
from pathlib import Path


def test_ddl_creates_4_tables():
    """验证 DDL 包含 4 张表的 CREATE 语句"""
    ddl_path = Path(__file__).parents[2] / "scripts" / "phase6_ddl.sql"
    content = ddl_path.read_text()
    assert "raw.ap_bank_statement" in content
    assert "std.ap_std_record" in content
    assert "dm.salesperson_mapping" in content
    assert "dm.salesperson_customer_mapping" in content
    assert "ReplacingMergeTree" in content
    assert "SETTINGS allow_experimental_object_type = 1" in content
    assert "UNIQUE (salesperson_id, customer_id)" in content
    # std.ap_std_record 去重键为 bank_transaction_no
    assert "ORDER BY (bank_transaction_no)" in content


def test_ddl_alters_report_records():
    """验证 DDL 包含 ALTER TABLE 扩展 report_records"""
    ddl_path = Path(__file__).parents[2] / "scripts" / "phase6_ddl.sql"
    content = ddl_path.read_text()
    assert "ALTER TABLE dm.report_records" in content
    assert "salesperson_id" in content
    assert "supplier_code" in content
