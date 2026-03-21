# services/customer360_service.py
"""客户360核心业务服务"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schemas.customer360 import (
    Customer360Record,
    Customer360Summary,
    CustomerDistribution,
    CustomerMergeQueue,
    CustomerTrend,
    MatchAction,
    MatchResult,
    MergeHistory,
    RawARRecord,
    RawCustomer,
)
from services.customer_matcher import CustomerMatcher
from services.customer_standardizer import CustomerStandardizer

logger = logging.getLogger(__name__)


class PaymentScoreCalculator:
    """付款信用分计算器（0-100分）

    评分规则：
    - 逾期率扣分：每 1% 逾期率扣 2 分
    - 付款及时性加分：90天内付款 +5 分
    - 账龄结构扣分：超90天账龄占比 > 30% 扣 10 分
    - 合作时长加分：首次合作 > 2年 加 5 分
    """

    def calculate(self, ar_records: list[RawARRecord]) -> float:
        if not ar_records:
            return 50.0

        score = 100.0

        # 逾期率扣分：每 1% 逾期率扣 2 分
        overdue_count = sum(1 for r in ar_records if r.is_overdue)
        overdue_rate = overdue_count / len(ar_records)
        score -= overdue_rate * 200

        # 超长账龄扣分：超90天占比 > 30% 扣 10 分
        long_aging = sum(1 for r in ar_records if r.overdue_days > 90)
        if long_aging / len(ar_records) > 0.3:
            score -= 10

        # 近期付款加分：90天内已付款占比 > 70% 加 5 分
        recent_paid = sum(
            1 for r in ar_records
            if not r.is_overdue
            and (date.today() - r.bill_date).days < 90
        )
        if recent_paid / len(ar_records) > 0.7:
            score += 5

        # 合作时长加分：首次合作 > 2年 加 5 分
        if ar_records:
            bill_dates = [r.bill_date for r in ar_records]
            earliest = min(bill_dates)
            if (date.today() - earliest).days > 730:  # 2 * 365
                score += 5

        return max(0.0, min(100.0, score))


class RiskLevelCalculator:
    """风险等级计算器"""

    def calculate(self, score: float, overdue_rate: float) -> str:
        if overdue_rate > 0.3 or score < 40:
            return "高"
        elif overdue_rate > 0.1 or score < 70:
            return "中"
        return "低"


class Customer360Generator:
    """客户360记录生成器"""

    def __init__(
        self,
        score_calc: PaymentScoreCalculator | None = None,
        risk_calc: RiskLevelCalculator | None = None,
    ):
        self._score_calc = score_calc or PaymentScoreCalculator()
        self._risk_calc = risk_calc or RiskLevelCalculator()

    def generate_from_match(
        self,
        matches: list[MatchResult],
        ar_by_customer: dict[str, list[RawARRecord]] | None = None,
        stat_date: date | None = None,
    ) -> list[Customer360Record]:
        """从匹配结果生成 360 记录（仅处理 auto_merge）"""
        records: list[Customer360Record] = []
        ar_by_customer = ar_by_customer or {}
        stat_date = stat_date or date.today()

        for match in matches:
            if match.action != MatchAction.AUTO_MERGE:
                continue

            customers = match.customers
            unified_code = match.unified_customer_code or ""

            # 聚合应收数据
            all_ar: list[RawARRecord] = []
            for c in customers:
                all_ar.extend(ar_by_customer.get(c.customer_id, []))

            ar_total = sum((r.bill_amount for r in all_ar), Decimal("0"))
            ar_overdue = sum((r.bill_amount for r in all_ar if r.is_overdue), Decimal("0"))
            overdue_rate = float(ar_overdue / ar_total) if ar_total > 0 else 0.0
            payment_score = self._score_calc.calculate(all_ar)
            risk_level = self._risk_calc.calculate(payment_score, overdue_rate)

            # 计算 last_payment_date 和 first_coop_date
            if all_ar:
                paid_dates = [r.bill_date for r in all_ar if not r.is_overdue]
                all_dates = [r.bill_date for r in all_ar]
                last_payment_date = min(paid_dates) if paid_dates else None
                first_coop_date = min(all_dates)
                company_code = max(all_ar, key=lambda r: float(r.bill_amount)).company_code
            else:
                last_payment_date = None
                first_coop_date = None
                company_code = None

            # 合并客户名称（取最长的规范化名称）
            customer_name = max((c.customer_name for c in customers), key=len)
            customer_short_name = customers[0].customer_short_name

            records.append(
                Customer360Record(
                    unified_customer_code=unified_code,
                    raw_customer_ids=[c.customer_id for c in customers],
                    source_systems=[c.source_system for c in customers],
                    customer_name=customer_name,
                    customer_short_name=customer_short_name,
                    ar_total=ar_total,
                    ar_overdue=ar_overdue,
                    overdue_rate=overdue_rate,
                    payment_score=payment_score,
                    risk_level=risk_level,
                    merge_status="auto_merged",
                    last_payment_date=last_payment_date,
                    first_coop_date=first_coop_date,
                    company_code=company_code,
                    stat_date=stat_date,
                    updated_at=datetime.now(),
                )
            )

        return records


class Customer360Service:
    """客户360主服务

    整合：连接器 → 标准化 → 匹配 → 360生成 → ClickHouse持久化
    """

    def __init__(
        self,
        ch_service: Any | None = None,
    ):
        self._ch = ch_service
        self._standardizer = CustomerStandardizer()
        self._matcher = CustomerMatcher()
        self._generator = Customer360Generator()

    def _get_ch_service(self):
        if self._ch is None:
            from api.dependencies import get_clickhouse_service
            self._ch = get_clickhouse_service()
        return self._ch

    def refresh(self, stat_date: date | None = None) -> dict[str, Any]:
        """执行全量刷新（每日批次调用）"""
        stat_date = stat_date or date.today()
        results: dict[str, Any] = {"stat_date": str(stat_date), "errors": []}

        # 步骤1: 拉取客户
        try:
            from connectors.customer import ERPCustomerConnectorRegistry
            raw_customers = ERPCustomerConnectorRegistry.fetch_all_customers()
            results["customers_fetched"] = len(raw_customers)
        except Exception as e:
            logger.error(f"拉取客户数据失败: {e}")
            results["errors"].append(f"fetch_customers: {e}")
            return results

        # 步骤2: 标准化
        std_customers = [self._standardizer.standardize(c) for c in raw_customers]
        results["customers_standardized"] = len(std_customers)

        # 步骤3: 匹配
        matches = self._matcher.match(std_customers)
        results["auto_merges"] = len([m for m in matches if m.action == MatchAction.AUTO_MERGE])
        results["pending"] = len([m for m in matches if m.action == MatchAction.PENDING])

        # 步骤4: 写入合并队列并发送飞书通知
        try:
            pending = [m for m in matches if m.action == MatchAction.PENDING]
            self._upsert_merge_queue(pending)
            if pending:
                from services.feishu.feishu_client import FeishuClient
                feishu = FeishuClient()
                ch = self._get_ch_service()
                queue_items = ch.get_merge_queue("pending")
                feishu.send_merge_notification(queue_items)
        except Exception as e:
            logger.error(f"写入合并队列/飞书通知失败: {e}")
            results["errors"].append(f"merge_queue: {e}")

        # 步骤5: 生成并持久化 360 记录
        try:
            records = self._generator.generate_from_match(matches, stat_date=stat_date)
            ch = self._get_ch_service()
            ch.insert_customer360(records)
            results["records_persisted"] = len(records)
        except Exception as e:
            logger.error(f"持久化360记录失败: {e}")
            results["errors"].append(f"persist: {e}")

        return results

    def _upsert_merge_queue(self, pending_matches: list[MatchResult]) -> None:
        """将待复核匹配写入 ClickHouse merge_queue 表"""
        items = [
            CustomerMergeQueue(
                id=f"mq_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}",
                match_result=m,
            )
            for i, m in enumerate(pending_matches)
        ]
        if items:
            ch = self._get_ch_service()
            ch.insert_merge_queue(items)

    def get_summary(self, stat_date: date | None = None) -> Customer360Summary:
        """管理层视角客户360汇总"""
        d = stat_date or date.today()
        return self._get_ch_service().get_customer360_summary(d)

    def get_distribution(self, stat_date: date | None = None) -> CustomerDistribution:
        """客户分布数据"""
        d = stat_date or date.today()
        return self._get_ch_service().get_customer360_distribution(d)

    def get_trend(self, months: int = 12) -> CustomerTrend:
        """客户/应收趋势"""
        return self._get_ch_service().get_customer360_trend(months)

    def get_customer_detail(self, customer_code: str) -> dict[str, Any]:
        """单个客户360详情"""
        return self._get_ch_service().get_customer360_detail(customer_code)

    def get_merge_queue(self, status: str = "pending") -> list[CustomerMergeQueue]:
        """获取合并复核队列"""
        return self._get_ch_service().get_merge_queue(status)

    def confirm_merge(self, queue_id: str) -> dict[str, Any]:
        """确认合并"""
        return self._get_ch_service().confirm_merge(queue_id, operator="api")

    def reject_merge(self, queue_id: str) -> dict[str, Any]:
        """拒绝合并"""
        return self._get_ch_service().reject_merge(queue_id, operator="api")

    def undo_merge(
        self,
        unified_customer_code: str,
        original_customer_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """撤销合并"""
        return self._get_ch_service().undo_merge(
            unified_customer_code=unified_customer_code,
            original_customer_id=original_customer_id,
            operator="api",
            reason=reason,
        )

    def get_attribution_data(self, start_date: date, end_date: date) -> dict[str, Any]:
        """AI 归因数据"""
        return self._get_ch_service().get_customer_attribution(start_date, end_date)
