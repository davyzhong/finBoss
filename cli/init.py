"""finboss init - 初始化命令"""
import logging
import os
from pathlib import Path

import typer
from clickhouse_driver.errors import Error as ClickHouseError
from rich.console import Console

from cli.root import app

console = Console()
init_cli = typer.Typer(name="init", help="初始化数据库和知识库")

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# finboss init phase5
# ---------------------------------------------------------------------------
BUILTIN_ALERT_RULES = [
    {"id": "rule_overdue_rate", "name": "客户逾期率超标", "metric": "overdue_rate",
     "operator": "gt", "threshold": 0.3, "scope_type": "company", "scope_value": "",
     "alert_level": "高", "enabled": 1},
    {"id": "rule_overdue_amount", "name": "单客户逾期金额超标", "metric": "overdue_amount",
     "operator": "gt", "threshold": 1_000_000.0, "scope_type": "company", "scope_value": "",
     "alert_level": "高", "enabled": 1},
    {"id": "rule_overdue_delta", "name": "逾期率周环比恶化", "metric": "overdue_rate_delta",
     "operator": "gt", "threshold": 0.05, "scope_type": "company", "scope_value": "",
     "alert_level": "中", "enabled": 1},
    {"id": "rule_new_overdue", "name": "新增逾期客户", "metric": "new_overdue_count",
     "operator": "gt", "threshold": 5.0, "scope_type": "company", "scope_value": "",
     "alert_level": "中", "enabled": 1},
    {"id": "rule_aging_90", "name": "账龄超90天占比高", "metric": "aging_90pct",
     "operator": "gt", "threshold": 0.2, "scope_type": "company", "scope_value": "",
     "alert_level": "高", "enabled": 1},
]


@init_cli.command("phase5")
def init_phase5(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """初始化 Phase 5 相关表（告警规则、报告记录）"""
    from services.clickhouse_service import ClickHouseDataService

    ch = ClickHouseDataService()
    project_root = Path(__file__).parent.parent
    ddl_path = project_root / "scripts" / "phase5_ddl.sql"

    if not ddl_path.exists():
        console.print(f"[red]✗ DDL 文件不存在: {ddl_path}[/red]")
        raise typer.Exit(1)

    with open(ddl_path) as f:
        ddl_content = f.read()

    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            parts = stmt.split("CREATE TABLE IF NOT EXISTS ")
            table_name = parts[-1].split("(")[0].strip() if len(parts) > 1 else "unknown"
            console.print(f"  [green]✓[/green] {table_name}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                parts = stmt.split("CREATE TABLE IF NOT EXISTS ")
                table_name = parts[-1].split("(")[0].strip() if len(parts) > 1 else "unknown"
                console.print(f"  [dim]—[/dim] {table_name} (已存在)")
            else:
                console.print(f"  [red]✗ FAIL: {e}[/red]")

    # 插入内置告警规则
    console.print("\n[bold]插入内置告警规则:[/bold]")
    for rule in BUILTIN_ALERT_RULES:
        try:
            ch.execute(
                "INSERT INTO dm.alert_rules "
                "(id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at) "
                "VALUES (%(id)s, %(name)s, %(metric)s, %(operator)s, %(threshold)s, %(scope_type)s, %(scope_value)s, %(alert_level)s, %(enabled)s, now(), now())",
                rule,
            )
            console.print(f"  [green]✓[/green] {rule['name']}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                console.print(f"  [dim]—[/dim] {rule['name']} (已存在)")
            else:
                console.print(f"  [red]✗ FAIL: {rule['name']}: {e}[/red]")

    # 管理频道
    mgmt_channel = os.environ.get("FEISHU_MGMT_CHANNEL_ID", "").strip()
    if mgmt_channel:
        try:
            ch.execute(
                "INSERT INTO dm.report_recipients "
                "(id, recipient_type, name, channel_id, enabled, created_at) "
                "VALUES (%(id)s, %(type)s, %(name)s, %(channel_id)s, %(enabled)s, now())",
                {"id": "mgmt_1", "type": "management", "name": "财务总监群",
                 "channel_id": mgmt_channel, "enabled": 1},
            )
            console.print("  [green]✓[/green] dm.report_recipients (mgmt_1)")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                console.print("  [dim]—[/dim] dm.report_recipients (mgmt_1 已存在)")
            else:
                console.print(f"  [red]✗ FAIL dm.report_recipients: {e}[/red]")
    else:
        console.print("  [yellow]⚠[/yellow] 跳过 report_recipients (FEISHU_MGMT_CHANNEL_ID 未设置)")

    console.print("\n[bold green]✓ Phase 5 初始化完成！[/bold green]")


# ---------------------------------------------------------------------------
# finboss init customer360
# ---------------------------------------------------------------------------
@init_cli.command("customer360")
def init_customer360(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """初始化客户360相关表"""
    from services.clickhouse_service import ClickHouseDataService

    ch = ClickHouseDataService()
    project_root = Path(__file__).parent.parent
    ddl_path = project_root / "scripts" / "customer360_ddl.sql"

    if not ddl_path.exists():
        console.print(f"[red]✗ DDL 文件不存在: {ddl_path}[/red]")
        raise typer.Exit(1)

    with open(ddl_path) as f:
        ddl_content = f.read()

    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            parts = stmt.split("CREATE TABLE IF NOT EXISTS ")
            table_name = parts[-1].split("(")[0].strip() if len(parts) > 1 else "unknown"
            console.print(f"  [green]✓[/green] {table_name}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                parts = stmt.split("CREATE TABLE IF NOT EXISTS ")
                table_name = parts[-1].split("(")[0].strip() if len(parts) > 1 else "unknown"
                console.print(f"  [dim]—[/dim] {table_name} (已存在)")
            else:
                console.print(f"  [red]✗ FAIL: {e}[/red]")

    console.print("\n[bold green]✓ 客户360初始化完成！[/bold green]")


# ---------------------------------------------------------------------------
# finboss init knowledge
# ---------------------------------------------------------------------------
FINANCIAL_KNOWLEDGE = [
    {"category": "financial_accounting", "content": "应收账款（1122）是核算企业因销售商品、提供劳务等经营活动应收取的款项。包括销售货物、提供服务产生的应收款项，以及代购货方垫付的各种款项。借方登记增加，贷方登记减少，期末余额在借方表示尚未收回的应收款项。",
     "metadata": {"subject_code": "1122", "subject_name": "应收账款", "type": "资产类"}},
    {"category": "indicator_definition", "content": "AR（Accounts Receivable）应收总额 = Σ(每笔应收单据金额)。指企业在一定时期内因销售商品、提供劳务等经营活动产生的全部应收账款余额，反映企业对客户的信用规模。",
     "metadata": {"indicator": "AR", "full_name": "Accounts Receivable", "unit": "元"}},
    {"category": "indicator_definition", "content": "逾期率 = 逾期金额 ÷ 应收总额 × 100%。该指标反映应收账款的质量和信用风险管理水平。行业参考：制造业一般 < 15%，零售业 < 10%，上市公司财报通常要求 < 5%。",
     "metadata": {"indicator": "overdue_rate", "formula": "逾期金额/应收总额×100%", "unit": "%"}},
    {"category": "indicator_definition", "content": "回款率 = 实收金额 ÷ 应收总额 × 100%。衡量企业收账效率的关键指标。月末回款率目标通常 > 85%，季度回款率目标 > 95%。",
     "metadata": {"indicator": "collection_rate", "formula": "实收金额/应收总额×100%", "unit": "%"}},
    {"category": "business_rule", "content": "账龄分析分组：0-30天（正常）、31-60天（关注）、61-90天（预警）、91-180天（风险）、180天以上（不良）。账龄越长，回收风险越大，需重点催收。",
     "metadata": {"analysis_type": "aging", "dimension": "days"}},
    {"category": "business_rule", "content": "超账期处理流程：①逾期1-7天系统自动提醒 ②逾期8-30天业务员电话催收 ③逾期31-60天销售经理介入 ④逾期61天以上法务部介入。",
     "metadata": {"rule_type": "overdue", "process": "reminder -> call -> manager -> legal"}},
]


@init_cli.command("knowledge")
def init_knowledge(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
) -> None:
    """初始化财务知识库（Milvus）"""
    from services.ai import RAGService

    rag = RAGService()

    if not rag.is_available():
        console.print("[red]✗ Milvus 服务不可用，请先启动 docker-compose[/red]")
        console.print("   运行: docker-compose -f config/docker-compose.yml up -d")
        raise typer.Exit(1)

    console.print(f"[cyan]开始导入 {len(FINANCIAL_KNOWLEDGE)} 条财务知识...[/cyan]")

    categories: dict[str, int] = {}
    for doc in FINANCIAL_KNOWLEDGE:
        cat = doc["category"]
        categories[cat] = categories.get(cat, 0) + 1

    console.print("\n[bold]知识分布:[/bold]")
    for cat, count in categories.items():
        console.print(f"  - {cat}: {count} 条")

    ids = rag.ingest_batch(FINANCIAL_KNOWLEDGE)
    console.print(f"\n[green]✓ 成功导入 {len(ids)} 条知识[/green]")

    if verbose:
        console.print("\n[bold]验证检索:[/bold]")
        results = rag.search("逾期率如何计算", top_k=2)
        console.print(f"  查询'逾期率如何计算'返回 {len(results)} 条结果")
        if results:
            console.print(f"  Top1: {results[0]['content'][:80]}...")

    console.print("\n[bold green]✓ 财务知识库初始化完成！[/bold green]")


app.add_typer(init_cli, name="init")
