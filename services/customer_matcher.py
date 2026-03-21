# services/customer_matcher.py
"""客户匹配引擎"""
import difflib
import hashlib

from schemas.customer360 import MatchAction, MatchResult, RawCustomer


class CustomerMatcher:
    """客户匹配引擎

    两层匹配策略：
    1. 精确匹配：tax_id / credit_code 完全相同 → 直接合并
    2. 模糊匹配：基于名称相似度（difflib.SequenceMatcher）
    """

    SIMILARITY_HIGH = 0.95  # 自动合并阈值
    SIMILARITY_MED = 0.85   # 人工复核阈值

    def match(self, customers: list[RawCustomer]) -> list[MatchResult]:
        """对客户列表进行匹配，返回匹配结果列表"""
        results: list[MatchResult] = []
        seen: set[str] = set()

        for i, c1 in enumerate(customers):
            if c1.customer_id in seen:
                continue

            group = [c1]
            seen.add(c1.customer_id)

            for c2 in customers[i + 1:]:
                if c2.customer_id in seen:
                    continue

                similarity = self._calc_similarity(c1, c2)
                if similarity >= self.SIMILARITY_HIGH:
                    group.append(c2)
                    seen.add(c2.customer_id)
                elif similarity >= self.SIMILARITY_MED:
                    results.append(
                        MatchResult(
                            action=MatchAction.PENDING,
                            customers=[c1, c2],
                            similarity=similarity,
                            reason=f"名称相似度 {similarity:.2f}",
                        )
                    )

            if len(group) > 1:
                unified_code = self._generate_unified_code(group)
                results.append(
                    MatchResult(
                        action=MatchAction.AUTO_MERGE,
                        customers=group,
                        unified_customer_code=unified_code,
                        similarity=1.0,
                        reason="名称完全相同",
                    )
                )

        return results

    def _calc_similarity(self, c1: RawCustomer, c2: RawCustomer) -> float:
        """计算两个客户的相似度"""
        # 精确匹配（优先）
        if c1.tax_id and c1.tax_id == c2.tax_id:
            return 1.0
        if c1.credit_code and c1.credit_code == c2.credit_code:
            return 1.0

        # 模糊匹配
        name_sim = self._name_similarity(c1.customer_name, c2.customer_name)

        # 简称辅助验证（简称相同权重 +0.3）
        short_bonus = 0.0
        if c1.customer_short_name and c2.customer_short_name:
            if self._name_similarity(c1.customer_short_name, c2.customer_short_name) > 0.9:
                short_bonus = 0.3

        return min(name_sim + short_bonus, 1.0)

    def _generate_unified_code(self, customers: list[RawCustomer]) -> str:
        """为合并组生成统一客户编码（SHA256，固定12位十六进制前缀）"""
        first = customers[0]
        raw = f"{first.source_system}:{first.customer_id}"
        return f"C360_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    def _name_similarity(self, name1: str, name2: str) -> float:
        """基于字符串相似度计算名称相似度"""
        return difflib.SequenceMatcher(None, name1, name2).ratio()
