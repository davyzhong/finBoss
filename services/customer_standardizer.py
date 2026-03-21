# services/customer_standardizer.py
"""客户数据标准化服务"""
import re

from schemas.customer360 import RawCustomer


class CustomerStandardizer:
    """客户数据标准化

    标准化规则：
    - customer_name：去除空格、括号内容、全角转半角、去除常见后缀
    - customer_short_name：从标准化后的名称提取前4字符
    """

    COMMON_SUFFIXES = [
        "有限公司",
        "股份有限公司",
        "有限责任公司",
        "Ltd",
        "Ltd.",
        "Co.",
        "Co",
        "Inc.",
        "Inc",
    ]

    def standardize(self, customer: RawCustomer) -> RawCustomer:
        """标准化客户数据，返回新的 RawCustomer 实例（不修改原对象）"""
        name = customer.customer_name

        # 去除空格
        name = re.sub(r"\s+", "", name)

        # 去除括号及其内容：「腾讯计算机（深圳）」→「腾讯计算机」
        name = re.sub(r"[（(].*?[）)]", "", name)

        # 全角转半角
        name = self._fullwidth_to_halfwidth(name)

        # 去除常见后缀
        for suffix in self.COMMON_SUFFIXES:
            name = name.replace(suffix, "")

        short_name = self._extract_short_name(name)

        return customer.model_copy(
            update={
                "customer_name": name,
                "customer_short_name": short_name,
            }
        )

    def _fullwidth_to_halfwidth(self, text: str) -> str:
        """全角转半角"""
        result = []
        for char in text:
            if 0xFF01 <= ord(char) <= 0xFF5E:
                result.append(chr(ord(char) - 0xFEE0))
            else:
                result.append(char)
        return "".join(result)

    def _extract_short_name(self, name: str) -> str:
        """提取客户简称（标准化后的名称前4字符）"""
        return name[:4] if len(name) >= 4 else name
