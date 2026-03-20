#!/usr/bin/env python3
"""简单的测试数据插入脚本"""
import random
from datetime import datetime, timedelta

from clickhouse_driver import Client

# 连接 ClickHouse
client = Client(host='localhost', port=9002, database='std')

# 生成测试 AR 数据
print("正在生成测试 AR 数据...")

companies = [
    ("C001", "总公司"),
    ("C002", "华东分公司"),
    ("C003", "华南分公司"),
]

customers = [
    ("CU001", "阿里巴巴集团"),
    ("CU002", "腾讯科技"),
    ("CU003", "华为技术"),
    ("CU004", "字节跳动"),
    ("CU005", "美团点评"),
]

base_date = datetime.now().date()
data = []

for i in range(100):
    company = random.choice(companies)
    customer = random.choice(customers)
    bill_date = base_date - timedelta(days=random.randint(30, 365))
    due_date = bill_date + timedelta(days=random.randint(30, 90))
    bill_amount = random.uniform(10000, 1000000)
    received_amount = bill_amount * random.uniform(0, 1)
    overdue_days = max(0, (base_date - due_date).days)
    is_overdue = overdue_days > 0

    data.append({
        'id': f'AR{2024}{i:06d}',
        'stat_date': base_date,
        'company_code': company[0],
        'company_name': company[1],
        'customer_code': customer[0],
        'customer_name': customer[1],
        'bill_no': f'BILL{2024}{i:06d}',
        'bill_date': bill_date,
        'due_date': due_date,
        'bill_amount': round(bill_amount, 2),
        'received_amount': round(received_amount, 2),
        'allocated_amount': round(received_amount * 0.9, 2),
        'unallocated_amount': round(bill_amount - received_amount, 2),
        'aging_bucket': f'{overdue_days}d',
        'aging_days': overdue_days,
        'is_overdue': is_overdue,
        'overdue_days': overdue_days if is_overdue else 0,
        'status': 'active',
        'etl_time': datetime.now(),
    })

# 插入数据
client.execute(
    'INSERT INTO std_ar VALUES',
    data
)

print(f"✓ 成功插入 {len(data)} 条 AR 记录")

# 汇总数据
print("正在生成汇总数据...")

dm_client = Client(host='localhost', port=9002, database='dm')

# 按公司汇总
summary_data = []
for company in companies:
    company_records = [d for d in data if d['company_code'] == company[0]]
    if company_records:
        total_amount = sum(d['bill_amount'] for d in company_records)
        received = sum(d['received_amount'] for d in company_records)
        overdue_records = [d for d in company_records if d['is_overdue']]
        overdue_amount = sum(d['bill_amount'] - d['received_amount'] for d in overdue_records)

        summary_data.append({
            'stat_date': base_date,
            'company_code': company[0],
            'company_name': company[1],
            'total_ar_amount': round(total_amount, 2),
            'received_amount': round(received, 2),
            'allocated_amount': round(received * 0.9, 2),
            'unallocated_amount': round(total_amount - received, 2),
            'overdue_amount': round(overdue_amount, 2),
            'overdue_count': len(overdue_records),
            'total_count': len(company_records),
            'overdue_rate': round(len(overdue_records) / len(company_records), 4) if company_records else 0,
            'aging_0_30': round(total_amount * 0.4, 2),
            'aging_31_60': round(total_amount * 0.3, 2),
            'aging_61_90': round(total_amount * 0.2, 2),
            'aging_91_180': round(total_amount * 0.08, 2),
            'aging_180_plus': round(total_amount * 0.02, 2),
            'etl_time': datetime.now(),
        })

dm_client.execute(
    'INSERT INTO dm_ar_summary VALUES',
    summary_data
)

print(f"✓ 成功插入 {len(summary_data)} 条汇总记录")

# 按客户汇总
customer_data = []
for customer in customers:
    customer_records = [d for d in data if d['customer_code'] == customer[0]]
    if customer_records:
        total_amount = sum(d['bill_amount'] for d in customer_records)
        overdue_records = [d for d in customer_records if d['is_overdue']]
        overdue_amount = sum(d['bill_amount'] - d['received_amount'] for d in overdue_records)
        last_bill = max(d['bill_date'] for d in customer_records)

        customer_data.append({
            'stat_date': base_date,
            'customer_code': customer[0],
            'customer_name': customer[1],
            'company_code': records[0]['company_code'] if (records := customer_records) else '',
            'total_ar_amount': round(total_amount, 2),
            'overdue_amount': round(overdue_amount, 2),
            'overdue_count': len(overdue_records),
            'total_count': len(customer_records),
            'overdue_rate': round(len(overdue_records) / len(customer_records), 4) if customer_records else 0,
            'last_bill_date': last_bill,
            'etl_time': datetime.now(),
        })

dm_client.execute(
    'INSERT INTO dm_customer_ar VALUES',
    customer_data
)

print(f"✓ 成功插入 {len(customer_data)} 条客户汇总记录")
print("\n========================================")
print("测试数据生成完成！")
print("========================================")
