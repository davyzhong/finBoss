#!/usr/bin/env python3
"""测试配置加载"""
from api.config import get_settings

try:
    settings = get_settings()
    print("✓ 配置加载成功!")
    print(f"Kingdee配置:")
    print(f"  - host: {settings.kingdee.host}")
    print(f"  - port: {settings.kingdee.port}")
    print(f"  - name: {settings.kingdee.name}")
    print(f"  - user: {settings.kingdee.user}")
    print(f"  - password: {'*' * len(settings.kingdee.password)} chars")  # Mask password
    print(f"\nApp配置:")
    print(f"  - app_name: {settings.app.app_name}")
    print(f"  - app_version: {settings.app.app_version}")
    print(f"  - debug: {settings.app.debug}")
except Exception as e:
    print(f"✗ 配置加载失败: {e}")
    import traceback
    traceback.print_exc()
