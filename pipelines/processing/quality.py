# pipelines/processing/quality.py
"""数据质量检查"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class QualityLevel(Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class QualityResult:
    rule_name: str
    level: QualityLevel
    passed: bool
    message: str
    details: dict[str, Any] | None = None
    checked_at: datetime = field(default_factory=datetime.now)


class DataQualityChecker:
    """数据质量检查器"""

    def __init__(self):
        self.results: list[QualityResult] = []

    def check_bill_no_not_null(self, records: list[dict]) -> QualityResult:
        null_count = sum(1 for r in records if not r.get("bill_no"))
        total = len(records)
        if null_count > 0:
            return QualityResult(
                rule_name="bill_no_not_null",
                level=QualityLevel.FAIL,
                passed=False,
                message=f"{null_count}/{total} 条记录 bill_no 为空",
            )
        return QualityResult(
            rule_name="bill_no_not_null",
            level=QualityLevel.PASS,
            passed=True,
            message="bill_no 全部非空",
        )

    def check_bill_amount_positive(self, records: list[dict]) -> QualityResult:
        invalid = [r for r in records if r.get("bill_amount", 0) <= 0]
        total = len(records)
        if invalid:
            return QualityResult(
                rule_name="bill_amount_positive",
                level=QualityLevel.FAIL,
                passed=False,
                message=f"{len(invalid)}/{total} 条记录 bill_amount <= 0",
            )
        return QualityResult(
            rule_name="bill_amount_positive",
            level=QualityLevel.PASS,
            passed=True,
            message="bill_amount 全部 > 0",
        )

    def check_no_duplicate(self, records: list[dict], key: str) -> QualityResult:
        seen = set()
        duplicates = 0
        for r in records:
            k = r.get(key)
            if k in seen:
                duplicates += 1
            seen.add(k)
        if duplicates > 0:
            return QualityResult(
                rule_name=f"no_duplicate_{key}",
                level=QualityLevel.FAIL,
                passed=False,
                message=f"发现 {duplicates} 条 {key} 重复",
            )
        return QualityResult(
            rule_name=f"no_duplicate_{key}",
            level=QualityLevel.PASS,
            passed=True,
            message=f"{key} 无重复",
        )

    def add_result(self, result: QualityResult) -> None:
        self.results.append(result)

    def get_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for r in self.results if r.passed)
        return passed / len(self.results)

    def get_summary(self) -> dict[str, Any]:
        return {
            "total_rules": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "pass_rate": self.get_pass_rate(),
        }
