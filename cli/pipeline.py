"""finboss pipeline - 数据管道管理命令"""
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cli.root import app

console = Console()
pipeline_cli = typer.Typer(name="pipeline", help="数据管道管理")


# ---------------------------------------------------------------------------
# finboss pipeline list
# ---------------------------------------------------------------------------
SEATUNNEL_JOBS = [
    ("kingdee_ar_batch", "kingdee_ar_batch.yml", "BATCH", "Kingdee AR 历史数据批量同步"),
    ("kingdee_ar_cdc", "kingdee_ar_cdc.yml", "STREAMING", "Kingdee AR CDC 实时同步"),
]


@pipeline_cli.command("list")
def pipeline_list() -> None:
    """列出所有已配置的数据管道"""
    table = Table(title="已配置的数据管道", show_header=True, header_style="bold cyan")
    table.add_column("名称", style="bold")
    table.add_column("文件", style="dim")
    table.add_column("模式", justify="center")
    table.add_column("描述")
    for name, file, mode, desc in SEATUNNEL_JOBS:
        mode_style = "yellow" if mode == "STREAMING" else "blue"
        table.add_row(name, file, f"[{mode_style}]{mode}[/{mode_style}]", desc)
    console.print(table)


# ---------------------------------------------------------------------------
# finboss pipeline trigger
# ---------------------------------------------------------------------------
@pipeline_cli.command("trigger")
def pipeline_trigger(
    job: str = typer.Argument(
        ...,
        autocompletion=lambda: [name for name, _, _, _ in SEATUNNEL_JOBS],
        help="管道任务名",
    ),
    mode: str = typer.Option("job", "--mode", "-m", help="运行模式 [job|standalone]"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """手动触发 SeaTunnel 数据管道"""
    job_map = {name: (file, desc) for name, file, _, desc in SEATUNNEL_JOBS}
    if job not in job_map:
        console.print(f"[red]✗ 未知任务: {job}[/red]")
        console.print("\n可用任务:")
        for name, _, _, desc in SEATUNNEL_JOBS:
            console.print(f"  - {name}: {desc}")
        raise typer.Exit(1)

    config_file, desc = job_map[job]
    config_path = (
        Path(__file__).parent.parent / "config" / "seatunnel" / "jobs" / config_file
    )
    if not config_path.exists():
        console.print(f"[red]✗ 配置文件不存在: {config_path}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]触发管道: {job}[/cyan]")
    console.print(f"  描述: {desc}")
    console.print(f"  配置文件: {config_path}")

    # 检查 docker container 是否存在
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}", "--filter", "name=seatunnel"],
        capture_output=True,
        text=True,
    )
    container_name = result.stdout.strip()
    if not container_name:
        console.print("[yellow]⚠ SeaTunnel 容器未运行，尝试启动...[/yellow]")
        compose_file = Path(__file__).parent.parent / "config" / "docker-compose.yml"
        subprocess.run(
            ["docker-compose", "-f", str(compose_file), "up", "-d", "seatunnel"],
            check=False,
        )
        console.print("[yellow]⚠ 已发送启动指令，请稍后检查状态[/yellow]")
    else:
        console.print(f"[green]✓ SeaTunnel 容器运行中: {container_name}[/green]")

    console.print("\n[yellow]提示:[/yellow] 请使用 SeaTunnel Web UI 或 API 提交任务:")
    console.print(f"  docker exec -it seatunnel sh -c 'seatunnel --job {config_path}'")
    console.print(f"\n[dim]配置文件路径: {config_path}[/dim]")


app.add_typer(pipeline_cli, name="pipeline")
