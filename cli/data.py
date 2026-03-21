"""finboss data - 数据管理命令"""
import random
from datetime import datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from cli.root import app

console = Console()
data_cli = typer.Typer(name="data", help="数据管理")


# ---------------------------------------------------------------------------
# finboss data seed
# ---------------------------------------------------------------------------
@data_cli.command("seed")
def data_seed(
    records: int = typer.Option(100, "--records", "-n", help="生成记录数"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """生成测试数据到 ClickHouse"""
    try:
        from clickhouse_driver import Client
    except ImportError:
        console.print("[red]缺少 clickhouse-driver，请运行: uv add clickhouse-driver[/red]")
        raise typer.Exit(1) from None

    console.print(f"[cyan]正在生成 {records} 条测试 AR 数据...[/cyan]")

    companies = [
        ("C001", "总公司"),
        ("C002", "华东分公司"),
        ("C003", "华南分公司"),
    ]
    customers = [
        ("CU001", "阿里巴巴集团"),
        ("CU002", "腾讯科技"),
        ("CU003", "华为技术"),
        ("CU004", "字节跳动"),
        ("CU005", "美团点评"),
    ]

    base_date = datetime.now().date()
    data: list[dict] = []

    for i in range(records):
        company = random.choice(companies)
        customer = random.choice(customers)
        bill_date = base_date - timedelta(days=random.randint(30, 365))
        due_date = bill_date + timedelta(days=random.randint(30, 90))
        bill_amount = random.uniform(10000, 1_000_000)
        received_amount = bill_amount * random.uniform(0, 1)
        overdue_days = max(0, (base_date - due_date).days)
        is_overdue = overdue_days > 0

        data.append({
            "id": f"AR{2024}{i:06d}",
            "stat_date": base_date,
            "company_code": company[0],
            "company_name": company[1],
            "customer_code": customer[0],
            "customer_name": customer[1],
            "bill_no": f"BILL{2024}{i:06d}",
            "bill_date": bill_date,
            "due_date": due_date,
            "bill_amount": round(bill_amount, 2),
            "received_amount": round(received_amount, 2),
            "allocated_amount": round(received_amount * 0.9, 2),
            "unallocated_amount": round(bill_amount - received_amount, 2),
            "aging_bucket": f"{overdue_days}d",
            "aging_days": overdue_days,
            "is_overdue": is_overdue,
            "overdue_days": overdue_days if is_overdue else 0,
            "status": "active",
            "etl_time": datetime.now(),
        })

    # 插入 std_ar
    client = Client(host="localhost", port=9002, database="std")
    client.execute("INSERT INTO std_ar VALUES", data)
    console.print(f"[green]✓ 成功插入 {len(data)} 条 AR 记录到 std.std_ar[/green]")

    # 插入 dm_ar_summary
    dm_client = Client(host="localhost", port=9002, database="dm")
    summary_data: list[dict] = []
    for company in companies:
        company_records = [d for d in data if d["company_code"] == company[0]]
        if not company_records:
            continue
        total_amount = sum(d["bill_amount"] for d in company_records)
        received = sum(d["received_amount"] for d in company_records)
        overdue_records = [d for d in company_records if d["is_overdue"]]
        overdue_amount = sum(d["bill_amount"] - d["received_amount"] for d in overdue_records)
        summary_data.append({
            "stat_date": base_date,
            "company_code": company[0],
            "company_name": company[1],
            "total_ar_amount": round(total_amount, 2),
            "received_amount": round(received, 2),
            "allocated_amount": round(received * 0.9, 2),
            "unallocated_amount": round(total_amount - received, 2),
            "overdue_amount": round(overdue_amount, 2),
            "overdue_count": len(overdue_records),
            "total_count": len(company_records),
            "overdue_rate": round(len(overdue_records) / len(company_records), 4),
            "aging_0_30": round(total_amount * 0.4, 2),
            "aging_31_60": round(total_amount * 0.3, 2),
            "aging_61_90": round(total_amount * 0.2, 2),
            "aging_91_180": round(total_amount * 0.08, 2),
            "aging_180_plus": round(total_amount * 0.02, 2),
            "etl_time": datetime.now(),
        })

    dm_client.execute("INSERT INTO dm_ar_summary VALUES", summary_data)
    console.print(f"[green]✓ 成功插入 {len(summary_data)} 条汇总记录到 dm.dm_ar_summary[/green]")

    # 插入 dm_customer_ar
    customer_data: list[dict] = []
    for customer in customers:
        cust_records = [d for d in data if d["customer_code"] == customer[0]]
        if not cust_records:
            continue
        total_amount = sum(d["bill_amount"] for d in cust_records)
        overdue_records = [d for d in cust_records if d["is_overdue"]]
        overdue_amount = sum(d["bill_amount"] - d["received_amount"] for d in overdue_records)
        last_bill = max(d["bill_date"] for d in cust_records)
        customer_data.append({
            "stat_date": base_date,
            "customer_code": customer[0],
            "customer_name": customer[1],
            "company_code": cust_records[0]["company_code"],
            "total_ar_amount": round(total_amount, 2),
            "overdue_amount": round(overdue_amount, 2),
            "overdue_count": len(overdue_records),
            "total_count": len(cust_records),
            "overdue_rate": round(len(overdue_records) / len(cust_records), 4),
            "last_bill_date": last_bill,
            "etl_time": datetime.now(),
        })

    dm_client.execute("INSERT INTO dm_customer_ar VALUES", customer_data)
    console.print(f"[green]✓ 成功插入 {len(customer_data)} 条客户汇总记录到 dm.dm_customer_ar[/green]")

    if verbose:
        table = Table(title="客户 AR 概览")
        table.add_column("客户", style="cyan")
        table.add_column("应收总额", justify="right")
        table.add_column("逾期金额", justify="right", style="red")
        table.add_column("逾期率", justify="right")
        for c in customer_data:
            table.add_row(
                c["customer_name"],
                f"¥{c['total_ar_amount']:,.0f}",
                f"¥{c['overdue_amount']:,.0f}",
                f"{c['overdue_rate']:.1%}",
            )
        console.print(table)

    console.print("\n[bold green]✓ 测试数据生成完成！[/bold green]")


# ---------------------------------------------------------------------------
# finboss data quality
# ---------------------------------------------------------------------------
@data_cli.command("quality")
def data_quality(
    table: str = typer.Option(
        ...,
        "--table",
        "-t",
        help="要检查的表名",
    ),
    max_delay: int = typer.Option(10, "--max-delay", "-d", help="最大延迟分钟数"),
    format: str = typer.Option("text", "--format", "-f", help="输出格式 [text|json]"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """执行数据质量检查"""
    import sys
    from pathlib import Path

    # 确保项目根目录在路径中
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from services.quality_service import QualityService

    quality_service = QualityService()
    latest_update = datetime.now()
    result = quality_service.check_timeliness(
        table_name=table,
        latest_update=latest_update,
        max_delay_minutes=max_delay,
    )
    quality_service.add_result(result)

    if format == "json":
        import json
        console.print(json.dumps(quality_service.get_summary(), indent=2, default=str))
        return

    summary = quality_service.get_summary()
    console.print(f"\n{'=' * 50}")
    console.print(f"[bold]数据质量检查报告 - {table}[/bold]")
    console.print(f"{'=' * 50}")
    console.print(f"  总规则数: {summary['total_rules']}")
    console.print(f"  [green]通过: {summary['passed']}[/green]")
    console.print(f"  [red]失败: {summary['failed']}[/red]")
    console.print(f"  [yellow]警告: {summary['warnings']}[/yellow]")
    console.print(f"  通过率: {summary['pass_rate']:.2%}")
    overall = "[green]✓ 通过[/green]" if summary["overall_pass"] else "[red]✗ 未通过[/red]"
    console.print(f"  总体状态: {overall}")

    if summary["results"]:
        console.print("\n[bold]详细结果:[/bold]")
        for r in summary["results"]:
            status = "[green]✓[/green]" if r["passed"] else "[red]✗[/red]"
            console.print(f"  [{status}] {r['rule_name']}: {r['message']}")


app.add_typer(data_cli, name="data")
