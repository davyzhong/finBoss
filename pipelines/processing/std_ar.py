# pipelines/processing/std_ar.py
"""AR 标准化处理"""
import hashlib
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from schemas.raw.kingdee import RawARVerify
from schemas.std.ar import StdARRecord

logger = logging.getLogger(__name__)


class ARStdProcessor:
    """AR 标准化处理器"""

    def process(self, raw_record: RawARVerify) -> StdARRecord:
        """将原始记录转换为标准层记录"""
        now = datetime.now()
        bill_date = raw_record.bill_date
        due_date = bill_date + timedelta(days=30) if bill_date else None

        aging_days = (now - bill_date).days if bill_date else 0
        if aging_days <= 30:
            aging_bucket = "0-30"
        elif aging_days <= 60:
            aging_bucket = "31-60"
        elif aging_days <= 90:
            aging_bucket = "61-90"
        elif aging_days <= 180:
            aging_bucket = "91-180"
        else:
            aging_bucket = "180+"

        is_overdue = aging_days > 30
        overdue_days = max(0, aging_days - 30) if is_overdue else 0

        record_id = hashlib.md5(
            f"{raw_record.source_id}{raw_record.bill_no}".encode()
        ).hexdigest()

        return StdARRecord(
            id=record_id,
            stat_date=now,
            company_code=str(raw_record.company_id),
            company_name="",
            customer_code=str(raw_record.customer_id),
            customer_name=raw_record.customer_name,
            bill_no=raw_record.bill_no,
            bill_date=bill_date,
            due_date=due_date,
            bill_amount=raw_record.bill_amount,
            received_amount=raw_record.payment_amount,
            allocated_amount=raw_record.allocate_amount,
            unallocated_amount=raw_record.unallocate_amount,
            currency="CNY",
            exchange_rate=1.0,
            bill_amount_base=raw_record.bill_amount,
            received_amount_base=raw_record.payment_amount,
            aging_bucket=aging_bucket,
            aging_days=aging_days,
            is_overdue=is_overdue,
            overdue_days=overdue_days,
            status=raw_record.status,
            document_status=raw_record.document_status,
            employee_name=None,
            dept_name=None,
            etl_time=now,
        )
