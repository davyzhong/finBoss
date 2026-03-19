# pipelines/marts/dm_ar.py
"""数据集市层 AR 生成"""
import logging
from datetime import datetime
from typing import Any

from schemas.dm.ar import DMCustomerAR, DMARSummary
from schemas.std.ar import StdARRecord

logger = logging.getLogger(__name__)


class ARMartGenerator:
    """AR 数据集市生成器"""

    def generate_summary(
        self,
        records: list[StdARRecord],
        stat_date: datetime | None = None,
    ) -> DMARSummary:
        """生成公司维度 AR 汇总"""
        if not records:
            stat_date = stat_date or datetime.now()
            return DMARSummary(
                stat_date=stat_date,
                company_code="", company_name="",
                total_ar_amount=0.0, received_amount=0.0, allocated_amount=0.0,
                unallocated_amount=0.0, overdue_amount=0.0, overdue_count=0,
                total_count=0, overdue_rate=0.0,
                aging_0_30=0.0, aging_31_60=0.0, aging_61_90=0.0,
                aging_91_180=0.0, aging_180_plus=0.0,
                etl_time=datetime.now(),
            )

        first = records[0]
        stat_date = stat_date or datetime.now()

        aging_buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "91-180": 0.0, "180+": 0.0}
        for r in records:
            aging_buckets[r.aging_bucket] = aging_buckets.get(r.aging_bucket, 0.0) + r.unallocated_amount

        overdue = [r for r in records if r.is_overdue]
        total_count = len(records)
        overdue_count = len(overdue)

        return DMARSummary(
            stat_date=stat_date,
            company_code=first.company_code,
            company_name=first.company_name,
            total_ar_amount=sum(r.bill_amount_base for r in records),
            received_amount=sum(r.received_amount_base for r in records),
            allocated_amount=sum(r.allocated_amount for r in records),
            unallocated_amount=sum(r.unallocated_amount for r in records),
            overdue_amount=sum(r.unallocated_amount for r in overdue),
            overdue_count=overdue_count,
            total_count=total_count,
            overdue_rate=round(overdue_count / total_count if total_count > 0 else 0.0, 4),
            aging_0_30=aging_buckets["0-30"],
            aging_31_60=aging_buckets["31-60"],
            aging_61_90=aging_buckets["61-90"],
            aging_91_180=aging_buckets["91-180"],
            aging_180_plus=aging_buckets["180+"],
            etl_time=datetime.now(),
        )

    def generate_customer_summary(
        self,
        records: list[StdARRecord],
        stat_date: datetime | None = None,
    ) -> DMCustomerAR:
        """生成客户维度 AR 汇总"""
        if not records:
            stat_date = stat_date or datetime.now()
            return DMCustomerAR(
                stat_date=stat_date,
                customer_code="", customer_name="", company_code="",
                total_ar_amount=0.0, overdue_amount=0.0, overdue_count=0,
                total_count=0, overdue_rate=0.0, etl_time=datetime.now(),
            )

        first = records[0]
        stat_date = stat_date or datetime.now()
        overdue = [r for r in records if r.is_overdue]
        total_count = len(records)
        overdue_count = len(overdue)
        last_bill_date = max((r.bill_date for r in records), default=None)

        return DMCustomerAR(
            stat_date=stat_date,
            customer_code=first.customer_code,
            customer_name=first.customer_name,
            company_code=first.company_code,
            total_ar_amount=sum(r.unallocated_amount for r in records),
            overdue_amount=sum(r.unallocated_amount for r in overdue),
            overdue_count=overdue_count,
            total_count=total_count,
            overdue_rate=round(overdue_count / total_count if total_count > 0 else 0.0, 4),
            last_bill_date=last_bill_date,
            etl_time=datetime.now(),
        )
