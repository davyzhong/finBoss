# pipelines/marts/ar_aggregations.py
"""AR 汇总计算公共逻辑（供 service 和 pipeline 共用）

提取自 ar_service.py 和 dm_ar.py 中的重复汇总逻辑。
"""
from datetime import datetime

from schemas.std.ar import StdARRecord


def aggregate_aging_buckets(records: list[StdARRecord]) -> dict[str, float]:
    """按账龄区间聚合未核销金额。

    Returns:
        {"0-30": float, "31-60": float, "61-90": float, "91-180": float, "180+": float}
    """
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "91-180": 0.0, "180+": 0.0}
    for r in records:
        buckets[r.aging_bucket] = buckets.get(r.aging_bucket, 0.0) + r.unallocated_amount
    return buckets


def filter_overdue(records: list[StdARRecord]) -> list[StdARRecord]:
    """返回所有逾期记录。"""
    return [r for r in records if r.is_overdue]


def calc_overdue_rate(overdue_count: int, total_count: int) -> float:
    """计算逾期率，保留 4 位小数。"""
    return round(overdue_count / total_count if total_count > 0 else 0.0, 4)
