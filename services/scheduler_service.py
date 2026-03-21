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


def _register_phase6_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册 Phase 6 调度任务：per-rep AR 报告"""

    def _per_salesperson_job(report_period: str) -> None:
        """通用报告生成函数，支持 weekly/monthly"""
        import logging

        logger3 = logging.getLogger(__name__)
        try:
            from services.per_salesperson_report_service import PerSalespersonReportService
            from services.feishu.feishu_client import FeishuClient

            svc = PerSalespersonReportService()
            files = svc.generate_for_all(report_period=report_period)
            if files:
                # 获取销售群配置
                from api.config import get_settings
                settings = get_settings()
                channel_id = settings.feishu.sales_channel_id
                if channel_id:
                    client = FeishuClient()
                    period_label = "周报" if report_period == "weekly" else "月报"
                    client.send_card_to_channel(
                        {
                            "elements": [
                                {
                                    "tag": "markdown",
                                    "content": (
                                        f"**📊 AR 业务员{period_label}已生成**\n"
                                        f"共 {len(files)} 位业务员的报告已就绪：\n"
                                        + "\n".join(f"- `{f.split('_')[-2]}`" for f in files[:5])
                                    ),
                                },
                                {
                                    "tag": "action",
                                    "actions": [{
                                        "tag": "button",
                                        "text": {"tag": "plain_text", "content": "查看报告"},
                                        "type": "primary",
                                        "url": "/static/reports/",
                                    }],
                                },
                            ]
                        },
                        channel_id=channel_id,
                    )
            logger3.info(f"[Phase6] Per-salesperson {report_period} reports: {len(files)} generated")
        except Exception as e:
            logger3.error(f"[Phase6] Per-salesperson {report_period} report failed: {e}")

    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        lambda: _per_salesperson_job("weekly"),
        CronTrigger(day_of_week="mon", hour=8, minute=5),
        id="phase6_per_salesperson_weekly",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _per_salesperson_job("monthly"),
        CronTrigger(day=1, hour=8, minute=5),
        id="phase6_per_salesperson_monthly",
        replace_existing=True,
    )


def _register_phase7a_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册 Phase 7A 调度任务：每日 06:00 数据质量检查"""

    def daily_quality_job() -> None:
        import logging
        logger7 = logging.getLogger(__name__)
        try:
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            result = svc.check_all()  # check_all calls generate_report_html internally
            svc.send_feishu_card()
            logger7.info(f"[Phase7A] Quality check done: {result['total_tables']} tables, {result['anomaly_count']} anomalies")
        except Exception as e:
            logger7.error(f"[Phase7A] Quality check failed: {e}", exc_info=True)

    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        daily_quality_job,
        CronTrigger(hour=6, minute=0),
        id="phase7a_daily_quality",
        name="数据质量每日检查",
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
    _register_phase6_jobs(_scheduler)
    _register_phase7a_jobs(_scheduler)
    _scheduler.start()
    logger.info("APScheduler 已启动，Phase 5 + Phase 6 + Phase 7A 调度任务已注册")
    return _scheduler


def stop_scheduler() -> None:
    """停止调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler 已停止")
