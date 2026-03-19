# services/quality_service.py
"""数据质量服务"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class QualityLevel(Enum):
    """质量等级"""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class QualityResult:
    """质量检查结果"""

    rule_name: str
    level: QualityLevel
    passed: bool
    message: str
    details: Optional[dict[str, Any]] = None
    checked_at: datetime = None

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.now()


class QualityService:
    """数据质量服务"""

    def __init__(self):
        self.results: list[QualityResult] = []

    def add_result(self, result: QualityResult) -> None:
        """添加质量检查结果"""
        self.results.append(result)

    def check_completeness(
        self,
        table_name: str,
        total_count: int,
        null_counts: dict[str, int],
        required_fields: list[str],
    ) -> QualityResult:
        """检查数据完整性

        Args:
            table_name: 表名
            total_count: 总记录数
            null_counts: 字段空值统计
            required_fields: 必填字段列表

        Returns:
            质量检查结果
        """
        failed_fields = []
        for field in required_fields:
            null_count = null_counts.get(field, 0)
            if null_count > 0:
                null_rate = null_count / total_count if total_count > 0 else 0
                failed_fields.append(f"{field}: {null_rate:.2%} null")

        if failed_fields:
            return QualityResult(
                rule_name=f"completeness_{table_name}",
                level=QualityLevel.FAIL,
                passed=False,
                message=f"必填字段存在空值: {', '.join(failed_fields)}",
                details={"null_counts": null_counts, "required_fields": required_fields},
            )

        return QualityResult(
            rule_name=f"completeness_{table_name}",
            level=QualityLevel.PASS,
            passed=True,
            message="数据完整性检查通过",
            details={"null_counts": null_counts},
        )

    def check_uniqueness(
        self,
        table_name: str,
        duplicate_count: int,
        unique_key: str,
    ) -> QualityResult:
        """检查数据唯一性

        Args:
            table_name: 表名
            duplicate_count: 重复记录数
            unique_key: 唯一键字段

        Returns:
            质量检查结果
        """
        if duplicate_count > 0:
            return QualityResult(
                rule_name=f"uniqueness_{table_name}",
                level=QualityLevel.FAIL,
                passed=False,
                message=f"唯一性检查失败: {unique_key} 存在 {duplicate_count} 条重复记录",
                details={"duplicate_count": duplicate_count, "unique_key": unique_key},
            )

        return QualityResult(
            rule_name=f"uniqueness_{table_name}",
            level=QualityLevel.PASS,
            passed=True,
            message=f"唯一性检查通过: {unique_key}",
        )

    def check_timeliness(
        self,
        table_name: str,
        latest_update: Optional[datetime],
        max_delay_minutes: int = 10,
    ) -> QualityResult:
        """检查数据及时性

        Args:
            table_name: 表名
            latest_update: 最新更新时间
            max_delay_minutes: 最大延迟分钟数

        Returns:
            质量检查结果
        """
        if latest_update is None:
            return QualityResult(
                rule_name=f"timeliness_{table_name}",
                level=QualityLevel.FAIL,
                passed=False,
                message="数据更新时间未知",
            )

        now = datetime.now()
        delay_minutes = (now - latest_update).total_seconds() / 60

        if delay_minutes > max_delay_minutes:
            return QualityResult(
                rule_name=f"timeliness_{table_name}",
                level=QualityLevel.WARNING,
                passed=False,
                message=f"数据延迟: {delay_minutes:.0f} 分钟，超过阈值 {max_delay_minutes} 分钟",
                details={"delay_minutes": delay_minutes, "latest_update": latest_update},
            )

        return QualityResult(
            rule_name=f"timeliness_{table_name}",
            level=QualityLevel.PASS,
            passed=True,
            message=f"数据及时性检查通过，延迟 {delay_minutes:.0f} 分钟",
            details={"delay_minutes": delay_minutes, "latest_update": latest_update},
        )

    def check_validity(
        self,
        table_name: str,
        invalid_count: int,
        total_count: int,
        field_name: str,
        valid_range: Optional[tuple[Any, Any]] = None,
    ) -> QualityResult:
        """检查数据有效性

        Args:
            table_name: 表名
            invalid_count: 无效记录数
            total_count: 总记录数
            field_name: 字段名
            valid_range: 有效范围（可选）

        Returns:
            质量检查结果
        """
        if total_count == 0:
            return QualityResult(
                rule_name=f"validity_{table_name}",
                level=QualityLevel.WARNING,
                passed=False,
                message=f"表 {table_name} 无数据",
            )

        invalid_rate = invalid_count / total_count
        threshold = 0.05

        if invalid_rate > threshold:
            return QualityResult(
                rule_name=f"validity_{table_name}",
                level=QualityLevel.FAIL,
                passed=False,
                message=f"{field_name} 无效率 {invalid_rate:.2%} 超过阈值 {threshold:.2%}",
                details={"invalid_count": invalid_count, "invalid_rate": invalid_rate},
            )

        return QualityResult(
            rule_name=f"validity_{table_name}",
            level=QualityLevel.PASS,
            passed=True,
            message=f"{field_name} 有效性检查通过",
            details={"invalid_count": invalid_count, "invalid_rate": invalid_rate},
        )

    def get_summary(self) -> dict[str, Any]:
        """获取质量检查汇总"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed and r.level == QualityLevel.FAIL)
        warnings = sum(1 for r in self.results if not r.passed and r.level == QualityLevel.WARNING)

        pass_rate = passed / total if total > 0 else 0.0

        return {
            "total_rules": total,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "pass_rate": round(pass_rate, 4),
            "overall_pass": pass_rate >= 0.95,
            "results": [
                {
                    "rule_name": r.rule_name,
                    "level": r.level.value,
                    "passed": r.passed,
                    "message": r.message,
                    "checked_at": r.checked_at.isoformat(),
                }
                for r in self.results
            ],
        }

    def reset(self) -> None:
        """重置检查结果"""
        self.results = []
