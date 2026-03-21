# services/ar_service.py
"""AR 应收业务服务"""
from datetime import datetime
from typing import Optional

from schemas.dm.ar import DMARSummary, DMCustomerAR
from schemas.std.ar import StdARRecord


class ARService:
    """AR 应收业务服务"""

    def __init__(self):
        pass

    def calculate_aging(
        self,
        bill_date: datetime,
        current_date: Optional[datetime] = None,
    ) -> tuple[int, str]:
        """计算账龄

        Args:
            bill_date: 应收日期
            current_date: 当前日期，默认为今天

        Returns:
            (账龄天数, 账龄区间)
        """
        if current_date is None:
            current_date = datetime.now()
        aging_days = (current_date - bill_date).days

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

        return aging_days, bucket

    def is_overdue(
        self,
        due_date: Optional[datetime],
        aging_days: int,
    ) -> tuple[bool, int]:
        """判断是否逾期

        Args:
            due_date: 到期日期
            aging_days: 账龄天数

        Returns:
            (是否逾期, 逾期天数)
        """
        if due_date is None:
            return aging_days > 30, max(0, aging_days - 30)
        current_date = datetime.now()
        if current_date > due_date:
            return True, (current_date - due_date).days
        return False, 0

    def summarize_by_company(
        self,
        records: list[StdARRecord],
        stat_date: Optional[datetime] = None,
    ) -> DMARSummary:
        """按公司汇总 AR 数据

        Args:
            records: 标准层 AR 记录列表
            stat_date: 统计日期

        Returns:
            公司维度汇总
        """
        if not records:
            stat_date = stat_date or datetime.now()
            return DMARSummary(
                stat_date=stat_date,
                company_code="",
                company_name="",
                total_ar_amount=0.0,
                received_amount=0.0,
                allocated_amount=0.0,
                unallocated_amount=0.0,
                overdue_amount=0.0,
                overdue_count=0,
                total_count=0,
                overdue_rate=0.0,
                aging_0_30=0.0,
                aging_31_60=0.0,
                aging_61_90=0.0,
                aging_91_180=0.0,
                aging_180_plus=0.0,
                etl_time=datetime.now(),
            )

        first_record = records[0]
        # 只在空记录时设置 stat_date，不覆盖调用者传入的值
        stat_date = stat_date or datetime.now()

        total_ar = sum(r.bill_amount_base for r in records)
        received = sum(r.received_amount_base for r in records)
        allocated = sum(r.allocated_amount for r in records)
        unallocated = sum(r.unallocated_amount for r in records)

        overdue_records = [r for r in records if r.is_overdue]
        overdue_amount = sum(r.unallocated_amount for r in overdue_records)
        overdue_count = len(overdue_records)
        total_count = len(records)
        overdue_rate = overdue_count / total_count if total_count > 0 else 0.0

        aging_0_30 = sum(r.unallocated_amount for r in records if r.aging_bucket == "0-30")
        aging_31_60 = sum(r.unallocated_amount for r in records if r.aging_bucket == "31-60")
        aging_61_90 = sum(r.unallocated_amount for r in records if r.aging_bucket == "61-90")
        aging_91_180 = sum(r.unallocated_amount for r in records if r.aging_bucket == "91-180")
        aging_180_plus = sum(r.unallocated_amount for r in records if r.aging_bucket == "180+")

        return DMARSummary(
            stat_date=stat_date,
            company_code=first_record.company_code,
            company_name=first_record.company_name,
            total_ar_amount=total_ar,
            received_amount=received,
            allocated_amount=allocated,
            unallocated_amount=unallocated,
            overdue_amount=overdue_amount,
            overdue_count=overdue_count,
            total_count=total_count,
            overdue_rate=round(overdue_rate, 4),
            aging_0_30=aging_0_30,
            aging_31_60=aging_31_60,
            aging_61_90=aging_61_90,
            aging_91_180=aging_91_180,
            aging_180_plus=aging_180_plus,
            etl_time=datetime.now(),
        )

    def summarize_by_customer(
        self,
        records: list[StdARRecord],
        stat_date: Optional[datetime] = None,
    ) -> DMCustomerAR:
        """按客户汇总 AR 数据

        Args:
            records: 标准层 AR 记录列表
            stat_date: 统计日期

        Returns:
            客户维度汇总
        """
        if not records:
            stat_date = stat_date or datetime.now()
            return DMCustomerAR(
                stat_date=stat_date,
                customer_code="",
                customer_name="",
                company_code="",
                total_ar_amount=0.0,
                overdue_amount=0.0,
                overdue_count=0,
                total_count=0,
                overdue_rate=0.0,
                etl_time=datetime.now(),
            )

        first_record = records[0]
        stat_date = stat_date or datetime.now()

        total_ar = sum(r.bill_amount_base for r in records)
        overdue_records = [r for r in records if r.is_overdue]
        overdue_amount = sum(r.unallocated_amount for r in overdue_records)
        overdue_count = len(overdue_records)
        total_count = len(records)
        overdue_rate = overdue_count / total_count if total_count > 0 else 0.0

        last_bill_date = max((r.bill_date for r in records), default=None)

        return DMCustomerAR(
            stat_date=stat_date,
            customer_code=first_record.customer_code,
            customer_name=first_record.customer_name,
            company_code=first_record.company_code,
            total_ar_amount=total_ar,
            overdue_amount=overdue_amount,
            overdue_count=overdue_count,
            total_count=total_count,
            overdue_rate=round(overdue_rate, 4),
            last_bill_date=last_bill_date,
            etl_time=datetime.now(),
        )
