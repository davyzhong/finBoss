"""FinBoss CLI entry point.

Usage:
    python -m cli
    finboss --help
"""
# 导入所有子命令模块以注册到 root app
from cli import data, init, pipeline, service  # noqa: F401
from cli.root import app  # noqa: F401

app()
