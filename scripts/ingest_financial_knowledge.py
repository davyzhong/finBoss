#!/usr/bin/env python3
"""财务知识库初始化脚本

向 Milvus 知识库中填充初始财务知识：
1. 财务科目体系（金蝶/标准科目映射）
2. 指标口径定义（AR/逾期率/账龄等）
3. 业务规则（账龄分类、超账期定义）
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai import RAGService

# ===========================================
# 初始财务知识库内容
# ===========================================

FINANCIAL_KNOWLEDGE = [
    # ---- 财务科目体系 ----
    {
        "category": "financial_accounting",
        "content": "应收账款（1122）是核算企业因销售商品、提供劳务等经营活动应收取的款项。包括销售货物、提供服务产生的应收款项，以及代购货方垫付的各种款项。借方登记增加，贷方登记减少，期末余额在借方表示尚未收回的应收款项。",
        "metadata": {"subject_code": "1122", "subject_name": "应收账款", "type": "资产类"},
    },
    {
        "category": "financial_accounting",
        "content": "金蝶K3系统中，应收账款初始余额录入在【系统设置】→【初始化】→【应收账款初始化】中进行，需要录入客户编码、期初余额、币别等信息。系统支持按客户、部门、业务员等多维度统计分析。",
        "metadata": {"system": "Kingdee K3", "module": "AR"},
    },
    {
        "category": "financial_accounting",
        "content": "坏账准备（1231）是应收账款的备抵科目，用于核算企业无法收回的应收账款。计提方法包括余额百分比法和账龄分析法。计提时借记'信用减值损失'，贷记'坏账准备'。实际发生坏账时，借记'坏账准备'，贷记'应收账款'。",
        "metadata": {"subject_code": "1231", "subject_name": "坏账准备", "type": "资产类（备抵）"},
    },
    {
        "category": "financial_accounting",
        "content": "应收账款周转率 = 营业收入 ÷ 平均应收账款余额。其中平均应收账款余额 = (期初应收账款 + 期末应收账款) ÷ 2。该指标反映企业应收账款周转速度，周转率越高说明资金回笼越快，信用管理越好。",
        "metadata": {"formula": "营业收入/平均应收账款", "unit": "次", "category": "运营效率"},
    },
    {
        "category": "financial_accounting",
        "content": "账龄分析是将应收账款按欠款时间长短进行分组的分析方法。常见分组：0-30天（正常）、31-60天（关注）、61-90天（预警）、91-180天（风险）、180天以上（不良）。账龄越长，回收风险越大，需重点催收。",
        "metadata": {"analysis_type": "aging", "dimension": "days"},
    },

    # ---- 指标口径定义 ----
    {
        "category": "indicator_definition",
        "content": "AR（Accounts Receivable）应收总额 = Σ(每笔应收单据金额)。指企业在一定时期内因销售商品、提供劳务等经营活动产生的全部应收账款余额，反映企业对客户的信用规模。计算时应包含已开票未到期和已逾期未收回的款项。",
        "metadata": {"indicator": "AR", "full_name": "Accounts Receivable", "unit": "元"},
    },
    {
        "category": "indicator_definition",
        "content": "逾期金额 = Σ(应收单据金额)，条件：is_overdue = 1 OR 到期日 < 当前日期 AND 状态 ≠ 已结清。指超过合同约定付款期限尚未收回的应收账款金额，是衡量企业资产质量和资金周转的重要指标。",
        "metadata": {"indicator": "overdue_amount", "condition": "is_overdue=1 OR due_date < today"},
    },
    {
        "category": "indicator_definition",
        "content": "逾期率 = 逾期金额 ÷ 应收总额 × 100%。该指标反映应收账款的质量和信用风险管理水平。行业参考：制造业一般 < 15%，零售业 < 10%，上市公司财报通常要求 < 5%。逾期率超过 20% 需重点关注信用风险。",
        "metadata": {"indicator": "overdue_rate", "formula": "逾期金额/应收总额×100%", "unit": "%"},
    },
    {
        "category": "indicator_definition",
        "content": "回款率 = 实收金额 ÷ 应收总额 × 100%。衡量企业收账效率的关键指标。月末回款率目标通常 > 85%，季度回款率目标 > 95%。回款率低于目标值说明存在催收压力，可能影响企业现金流。",
        "metadata": {"indicator": "collection_rate", "formula": "实收金额/应收总额×100%", "unit": "%"},
    },
    {
        "category": "indicator_definition",
        "content": "DSO（Days Sales Outstanding）销售账款回收天数 = 期末应收账款 ÷ 销售收入 × 365。反映企业从销售到收款所需的平均天数。DSO 越短说明资金周转越快。行业对比：制造业 DSO 约 45-90天，批发业约 30-60天。",
        "metadata": {"indicator": "DSO", "full_name": "Days Sales Outstanding", "unit": "天"},
    },
    {
        "category": "indicator_definition",
        "content": "逾期天数（Days Overdue）= 当前日期 - 到期日期。负值表示未到期，0 表示刚好到期，正值表示已逾期。该指标用于判断逾期严重程度：1-30天轻度逾期，31-90天中度逾期，91天以上重度逾期。重度逾期需启动法务催收。",
        "metadata": {"indicator": "days_overdue", "formula": "today - due_date", "unit": "天"},
    },

    # ---- 业务规则 ----
    {
        "category": "business_rule",
        "content": "超账期定义：超过合同约定付款期限即为超账期。标准付款期限：常规客户30天、重点客户60天、项目客户按里程碑。超账期处理流程：①逾期1-7天系统自动短信提醒 ②逾期8-30天业务员电话催收 ③逾期31-60天销售经理介入 ④逾期61天以上法务部介入。",
        "metadata": {"rule_type": "overdue", "process": "reminder -> call -> manager -> legal"},
    },
    {
        "category": "business_rule",
        "content": "信用额度管控规则：新客户初始信用额度为注册资本的 5%，最高不超过 100 万元。老客户根据历史回款记录动态调整：连续 3 个月回款率 > 95% 可上调 20%，出现逾期则立即冻结增量额度。超信用额度需经财务总监审批。",
        "metadata": {"rule_type": "credit_limit", "threshold": "注册资本×5%"},
    },
    {
        "category": "business_rule",
        "content": "应收账款确认规则：只有同时满足以下条件才能确认为应收账款：①已签订销售合同或订单 ②已完成发货或服务交付 ③已开具发票 ④客户已签收确认。任何一项不满足不得入账。期末未达账需进行暂估处理。",
        "metadata": {"rule_type": "recognition", "conditions": ["合同", "发货", "发票", "签收"]},
    },
    {
        "category": "business_rule",
        "content": "坏账核销标准：符合以下任一条件可申请坏账核销：①债务人依法宣告破产、关闭、解散，清算后仍无法收回 ②债务人死亡或失踪，遗产不足清偿且无继承人的 ③因自然灾害、战争等不可抗力导致无法收回。核销需经董事会审批并报税务机关备案。",
        "metadata": {"rule_type": "write_off", "conditions": ["破产清算", "债务人失踪", "不可抗力"]},
    },
    {
        "category": "business_rule",
        "content": "对账调整规则：客户对账差异处理原则：①金额差异 < 100元且双方确认的，以较小金额入账 ②金额差异 ≥ 100元的需逐笔核对原始单据 ③对方已付款我方未达账的，先确认收入后冲销 ④我方已记账对方未确认的，发送对账函待确认后调整。",
        "metadata": {"rule_type": "reconciliation", "threshold": 100},
    },
    {
        "category": "business_rule",
        "content": "AR 数据分析维度：常用分析维度包括：①按客户（customer_code/name）②按公司（company_code）③按账龄区间（0-30/31-60/61-90/91+）④按业务员（salesperson）⑤按产品线（product_category）⑥按地区（region）。FinBoss 系统支持多维度交叉分析。",
        "metadata": {"rule_type": "analysis_dimension", "dimensions": ["客户", "公司", "账龄", "业务员", "产品", "地区"]},
    },
]


def main() -> None:
    """初始化财务知识库"""
    print("=" * 60)
    print("FinBoss 财务知识库初始化")
    print("=" * 60)

    rag = RAGService()

    # 检查 Milvus 连接
    if not rag.is_available():
        print("❌ Milvus 服务不可用，请先启动 docker-compose")
        print("   运行: docker-compose -f config/docker-compose.yml up -d")
        sys.exit(1)

    print("✅ Milvus 连接正常")
    print(f"📦 开始导入 {len(FINANCIAL_KNOWLEDGE)} 条财务知识...")

    # 统计各类别数量
    categories: dict[str, int] = {}
    for doc in FINANCIAL_KNOWLEDGE:
        cat = doc["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print("\n知识分布:")
    for cat, count in categories.items():
        print(f"  - {cat}: {count} 条")

    # 批量导入
    ids = rag.ingest_batch(FINANCIAL_KNOWLEDGE)

    print(f"\n✅ 成功导入 {len(ids)} 条知识")
    print("\n可查询示例:")
    print('  "本月应收总额是多少"')
    print('  "哪些客户逾期了"')
    print('  "C001 公司的逾期率"')
    print('  "如何计算回款率"')

    # 验证检索
    print("\n🔍 验证检索功能...")
    results = rag.search("逾期率如何计算", top_k=2)
    print(f"   查询'逾期率如何计算'返回 {len(results)} 条结果")
    if results:
        print(f"   Top1: {results[0]['content'][:50]}...")

    print("\n" + "=" * 60)
    print("✅ 财务知识库初始化完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
