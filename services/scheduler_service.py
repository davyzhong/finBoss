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


def _register_phase5_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册 Phase 5 调度任务"""

    def daily_alert_job() -> None:
        """每日 09:00 逾期预警评估"""
        import logging

        logger2 = logging.getLogger(__name__)
        try:
            from services.alert_service import AlertService

            service = AlertService()
            alerts = service.evaluate_all()
            if alerts:
                service.send_summary(alerts)
            logger2.info(f"[Phase5] Alert evaluation: {len(alerts)} alerts triggered")
        except Exception as e:
            logger2.error(f"[Phase5] Alert evaluation failed: {e}")

    def daily_dashboard_job() -> None:
        """每日 02:30 生成管理看板"""
        import logging

        logger2 = logging.getLogger(__name__)
        try:
            from services.dashboard_service import DashboardService

            service = DashboardService()
            path = service.generate()
            logger2.info(f"[Phase5] Dashboard generated: {path}")
        except Exception as e:
            logger2.error(f"[Phase5] Dashboard generation failed: {e}")

    def weekly_report_job() -> None:
        """每周一 08:00 生成并发送周报"""
        import logging

        logger2 = logging.getLogger(__name__)
        try:
            from services.report_service import ReportService

            service = ReportService()
            path = service.generate("weekly")
            service.send_management_report("weekly")
            logger2.info(f"[Phase5] Weekly report generated: {path}")
        except Exception as e:
            logger2.error(f"[Phase5] Weekly report failed: {e}")

    def monthly_report_job() -> None:
        """每月1日 08:00 生成并发送月报"""
        import logging

        logger2 = logging.getLogger(__name__)
        try:
            from services.report_service import ReportService

            service = ReportService()
            path = service.generate("monthly")
            service.send_management_report("monthly")
            logger2.info(f"[Phase5] Monthly report generated: {path}")
        except Exception as e:
            logger2.error(f"[Phase5] Monthly report failed: {e}")

    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        daily_alert_job,
        CronTrigger(hour=9, minute=0),
        id="phase5_daily_alert",
        replace_existing=True,
    )
    scheduler.add_job(
        daily_dashboard_job,
        CronTrigger(hour=2, minute=30),
        id="phase5_daily_dashboard",
        replace_existing=True,
    )
    scheduler.add_job(
        weekly_report_job,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="phase5_weekly_report",
        replace_existing=True,
    )
    scheduler.add_job(
        monthly_report_job,
        CronTrigger(day=1, hour=8, minute=0),
        id="phase5_monthly_report",
        replace_existing=True,
    )


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
    _register_phase5_jobs(_scheduler)
    _scheduler.start()
    logger.info("APScheduler 已启动，Phase 5 调度任务已注册")
    return _scheduler


def stop_scheduler() -> None:
    """停止调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler 已停止")
