#!/usr/bin/env python
"""初始化客户360相关表和依赖配置"""
import sys
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    from services.clickhouse_service import ClickHouseDataService

    ch = ClickHouseDataService()

    # 读取 DDL 文件
    ddl_path = Path(__file__).parent / "customer360_ddl.sql"
    if not ddl_path.exists():
        logger.error(f"DDL 文件不存在: {ddl_path}")
        return

    with open(ddl_path) as f:
        ddl_content = f.read()

    # 逐条执行（ClickHouse 支持多语句）
    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            # 提取表名用于日志
            table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
            logger.info(f"  ✅ {table_name}")
        except Exception as e:
            logger.error(f"  ❌ 执行失败: {e}")

    logger.info("客户360初始化完成！")


if __name__ == "__main__":
    main()
