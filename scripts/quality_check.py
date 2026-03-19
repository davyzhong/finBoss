#!/usr/bin/env python3
"""数据质量检查脚本"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.quality_service import QualityService


def main():
    parser = argparse.ArgumentParser(description="FinBoss 数据质量检查")
    parser.add_argument(
        "--table",
        type=str,
        required=True,
        choices=["raw_kingdee.ar_verify", "std_ar", "dm_ar"],
        help="要检查的表名",
    )
    parser.add_argument(
        "--max-delay",
        type=int,
        default=10,
        help="最大延迟分钟数",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="text",
        choices=["text", "json"],
        help="输出格式",
    )
    args = parser.parse_args()

    quality_service = QualityService()

    # 模拟数据检查（实际应从元数据服务获取）
    latest_update = datetime.now()
    result = quality_service.check_timeliness(
        table_name=args.table,
        latest_update=latest_update,
        max_delay_minutes=args.max_delay,
    )
    quality_service.add_result(result)

    # 输出结果
    if args.format == "json":
        import json

        print(json.dumps(quality_service.get_summary(), indent=2, default=str))
    else:
        summary = quality_service.get_summary()
        print(f"\n{'=' * 50}")
        print(f"数据质量检查报告 - {args.table}")
        print(f"{'=' * 50}")
        print(f"总规则数: {summary['total_rules']}")
        print(f"通过: {summary['passed']}")
        print(f"失败: {summary['failed']}")
        print(f"警告: {summary['warnings']}")
        print(f"通过率: {summary['pass_rate']:.2%}")
        print(f"总体状态: {'✓ 通过' if summary['overall_pass'] else '✗ 未通过'}")
        print(f"\n详细结果:")
        for r in summary["results"]:
            status = "✓" if r["passed"] else "✗"
            print(f"  [{status}] {r['rule_name']}: {r['message']}")
        print()


if __name__ == "__main__":
    main()
