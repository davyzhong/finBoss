"""飞书应用配置（从 api/config.py 导入主配置）"""
from api.config import get_settings


def get_feishu_config():
    settings = get_settings()
    return settings.feishu
