"""Root Typer application with global options."""
import typer

from cli import __version__

app = typer.Typer(
    name="finboss",
    help="FinBoss - 企业财务AI数据平台命令行工具",
    add_completion=False,
)


@app.callback(
    invoke_without_command=True,
    context_settings={"allow_interspersed_args": False},
)
def callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="显示版本号"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出"),
    config: str = typer.Option("", "--config", "-c", help="配置文件路径"),
) -> None:
    """全局选项"""
    if version:
        console = typer.get_console()
        console.print(f"[bold]finboss[/bold] version [cyan]{__version__}[/cyan]")
        raise typer.Exit(0)
    ctx.meta["verbose"] = verbose
    ctx.meta["config"] = config
