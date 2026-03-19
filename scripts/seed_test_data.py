#!/usr/bin/env python3
"""测试数据填充脚本"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import create_engine, text

from api.config import get_settings


def create_test_tables(engine):
    """创建测试表"""
    print("[1/3] 创建测试表...")

    # std_ar 表
    engine.execute(text("""
        CREATE TABLE IF NOT EXISTS std.std_ar (
            id VARCHAR(64) PRIMARY KEY,
            stat_date DATETIME,
            company_code VARCHAR(32),
            company_name VARCHAR(128),
            customer_code VARCHAR(32),
            customer_name VARCHAR(128),
            bill_no VARCHAR(64),
            bill_date DATETIME,
            due_date DATETIME,
            bill_amount DECIMAL(18, 2),
            received_amount DECIMAL(18, 2),
            allocated_amount DECIMAL(18, 2),
            unallocated_amount DECIMAL(18, 2),
            aging_bucket VARCHAR(32),
            aging_days INT,
            is_overdue BOOLEAN,
            overdue_days INT DEFAULT 0,
            status VARCHAR(8),
            document_status VARCHAR(8),
            employee_name VARCHAR(64),
            dept_name VARCHAR(64),
            etl_time DATETIME
        )
    """))

    # dm_ar_summary 表
    engine.execute(text("""
        CREATE TABLE IF NOT EXISTS dm.dm_ar_summary (
            id INT AUTO_INCREMENT PRIMARY KEY,
            stat_date DATETIME,
            company_code VARCHAR(32),
            company_name VARCHAR(128),
            total_ar_amount DECIMAL(18, 2),
            received_amount DECIMAL(18, 2),
            allocated_amount DECIMAL(18, 2),
            unallocated_amount DECIMAL(18, 2),
            overdue_amount DECIMAL(18, 2),
            overdue_count INT,
            total_count INT,
            overdue_rate DECIMAL(5, 4),
            aging_0_30 DECIMAL(18, 2),
            aging_31_60 DECIMAL(18, 2),
            aging_61_90 DECIMAL(18, 2),
            aging_91_180 DECIMAL(18, 2),
            aging_180_plus DECIMAL(18, 2),
            etl_time DATETIME
        )
    """))

    # dm_customer_ar 表
    engine.execute(text("""
        CREATE TABLE IF NOT EXISTS dm.dm_customer_ar (
            id INT AUTO_INCREMENT PRIMARY KEY,
            stat_date DATETIME,
            customer_code VARCHAR(32),
            customer_name VARCHAR(128),
            company_code VARCHAR(32),
            total_ar_amount DECIMAL(18, 2),
            overdue_amount DECIMAL(18, 2),
            overdue_count INT,
            total_count INT,
            overdue_rate DECIMAL(5, 4),
            last_bill_date DATETIME,
            etl_time DATETIME
        )
    """))

    print("✓ 测试表创建完成")


def generate_test_data():
    """生成测试数据"""
    print("[2/3] 生成测试数据...")

    now = datetime.now()
    customers = [
        ("CU001", "客户A"),
        ("CU002", "客户B"),
        ("CU003", "客户C"),
        ("CU004", "客户D"),
        ("CU005", "客户E"),
    ]
    companies = [
        ("C001", "华东分公司"),
        ("C002", "华北分公司"),
        ("C003", "华南分公司"),
    ]
    employees = ["张三", "李四", "王五", "赵六"]
    departments = ["销售部", "市场部", "商务部"]

    records = []
    for i in range(100):
        cust_code, cust_name = customers[i % len(customers)]
        comp_code, comp_name = companies[i % len(companies)]
        emp = employees[i % len(employees)]
        dept = departments[i % len(departments)]

        bill_date = now - timedelta(days=i * 3)
        due_date = bill_date + timedelta(days=30)
        aging_days = (now - bill_date).days

        if aging_days <= 30:
            bucket = "0-30"
        elif aging_days <= 60:
            bucket = "31-60"
        elif aging_days <= 90:
            bucket = "61-90"
        elif aging_days <= 180:
            bucket = "91-180"
        else:
            bucket = "180+"

        bill_amount = (i + 1) * 10000.0
        received = bill_amount * (i % 5) * 0.1
        allocated = received * 0.5
        unallocated = bill_amount - received
        is_overdue = now > due_date

        records.append({
            "id": f"rec-{i+1:04d}",
            "stat_date": now,
            "company_code": comp_code,
            "company_name": comp_name,
            "customer_code": cust_code,
            "customer_name": cust_name,
            "bill_no": f"AR{datetime.now().strftime('%Y%m%d')}{i+1:04d}",
            "bill_date": bill_date,
            "due_date": due_date,
            "bill_amount": bill_amount,
            "received_amount": received,
            "allocated_amount": allocated,
            "unallocated_amount": unallocated,
            "aging_bucket": bucket,
            "aging_days": aging_days,
            "is_overdue": is_overdue,
            "overdue_days": (now - due_date).days if is_overdue else 0,
            "status": "A",
            "document_status": "C",
            "employee_name": emp,
            "dept_name": dept,
            "etl_time": now,
        })

    print(f"✓ 生成 {len(records)} 条 AR 测试数据")
    return pd.DataFrame(records)


def insert_test_data(engine, df):
    """插入测试数据"""
    print("[3/3] 插入测试数据...")

    df.to_sql("std_ar", engine, schema="std", if_exists="replace", index=False)

    # 生成汇总数据
    summary = df.groupby(["stat_date", "company_code", "company_name"]).agg({
        "bill_amount": "sum",
        "received_amount": "sum",
        "allocated_amount": "sum",
        "unallocated_amount": "sum",
        "is_overdue": ["sum", "count"],
    }).reset_index()
    summary.columns = [
        "stat_date", "company_code", "company_name",
        "total_ar_amount", "received_amount", "allocated_amount", "unallocated_amount",
        "overdue_amount", "overdue_count", "total_count"
    ]
    summary["overdue_rate"] = summary["overdue_count"] / summary["total_count"]
    summary["aging_0_30"] = df[df["aging_bucket"] == "0-30"].groupby(["stat_date", "company_code"])["unallocated_amount"].sum().values[0] if len(df[df["aging_bucket"] == "0-30"]) > 0 else 0
    summary["aging_31_60"] = 0
    summary["aging_61_90"] = 0
    summary["aging_91_180"] = 0
    summary["aging_180_plus"] = 0
    summary["etl_time"] = datetime.now()

    summary.to_sql("dm_ar_summary", engine, schema="dm", if_exists="replace", index=False)

    print(f"✓ 插入 {len(df)} 条 AR 数据")
    print(f"✓ 插入 {len(summary)} 条汇总数据")


def main():
    print("===========================================")
    print("FinBoss 测试数据填充")
    print("===========================================")

    settings = get_settings()

    try:
        engine = create_engine(
            settings.doris.connection_url,
            pool_pre_ping=True,
        )

        create_test_tables(engine)
        df = generate_test_data()
        insert_test_data(engine, df)

        print("")
        print("===========================================")
        print("测试数据填充完成！")
        print("===========================================")

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
