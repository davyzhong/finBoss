# services/scheduler_service.py
"""客户360每日调度服务"""
import logging
import os
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def daily_customer360_job() -> None:
    """每日02:00执行的客户360刷新任务"""
    logger.info("开始执行客户360每日刷新...")
    try:
        from services.customer360_service import Customer360Service

        service = Customer360Service()
        result = service.refresh(stat_date=date.today())
        logger.info(f"客户360刷新完成: {result}")
    except Exception as e:
        logger.error(f"客户360刷新失败: {e}", exc_info=True)


def start_scheduler() -> AsyncIOScheduler | None:
    """启动 APScheduler（仅在非测试环境）"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if os.environ.get("TESTING") == "1":
        logger.debug("测试环境，跳过调度器启动")
        return None

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        daily_customer360_job,
        "cron",
        hour=2,
        minute=0,
        id="customer360_daily",
        name="客户360每日刷新",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler 已启动，客户360每日刷新任务已注册（02:00）")
    return _scheduler


def stop_scheduler() -> None:
    """停止调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler 已停止")
