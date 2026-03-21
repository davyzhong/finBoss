"""finboss service - 服务管理命令"""
import socket
from urllib.error import URLError
from urllib.request import urlopen

import typer
from rich.console import Console
from rich.table import Table

from cli.root import app

console = Console()
service_cli = typer.Typer(name="service", help="服务状态检查")


def _check_tcp(host: str, port: int) -> tuple[str, bool]:
    """检查 TCP 端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex((host, port))
        ok = result == 0
        return ("UP" if ok else "DOWN", ok)
    except Exception:
        return ("DOWN", False)
    finally:
        sock.close()


def _check_http(host: str, port: int) -> tuple[str, bool]:
    """检查 HTTP 端口是否响应"""
    url = f"http://{host}:{port}"
    try:
        with urlopen(url, timeout=3) as resp:
            return (f"UP ({resp.status})", True)
    except URLError as e:
        return (f"DOWN ({e.reason})", False)
    except Exception as e:
        return (f"DOWN ({e})", False)


# 服务配置: (name, host, port, check_fn)
SERVICES = [
    ("ClickHouse (native)", "localhost", 9002, _check_tcp),
    ("ClickHouse (HTTP)", "localhost", 8123, _check_http),
    ("Kafka", "localhost", 9092, _check_tcp),
    ("MinIO API", "localhost", 9000, _check_http),
    ("MinIO Console", "localhost", 9001, _check_http),
    ("Milvus", "localhost", 19530, _check_tcp),
    ("Ollama", "localhost", 11434, _check_http),
    ("Nessie (Iceberg)", "localhost", 19120, _check_http),
]


# ---------------------------------------------------------------------------
# finboss service status
# ---------------------------------------------------------------------------
@service_cli.command("status")
def service_status(
    service_name: str | None = typer.Argument(None, help="检查指定服务，不指定则检查全部"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """检查所有依赖服务的健康状态"""
    if service_name:
        targets = [(s, h, p, f) for s, h, p, f in SERVICES if s.lower() == service_name.lower()]
        if not targets:
            console.print(f"[red]未知服务: {service_name}[/red]")
            console.print("\n可用服务:")
            for s, _, _, _ in SERVICES:
                console.print(f"  - {s}")
            raise typer.Exit(1)
    else:
        targets = SERVICES

    table = Table(title="FinBoss 服务状态", show_header=True, header_style="bold cyan")
    table.add_column("服务", style="bold")
    table.add_column("地址", justify="center")
    table.add_column("状态", justify="center")
    table.add_column("详情", style="dim")

    all_ok = True
    for name, host, port, checker in targets:
        status, ok = checker(host, port)
        all_ok = all_ok and ok
        style = "green" if ok else "red"
        addr = f"{host}:{port}"
        table.add_row(name, addr, f"[{style}]{status}[/{style}]", "")

    console.print(table)

    if all_ok:
        console.print("\n[bold green]✓ 所有服务运行正常[/bold green]")
    else:
        console.print("\n[bold yellow]⚠ 部分服务不可用，请检查 docker-compose[/bold yellow]")


app.add_typer(service_cli, name="service")
