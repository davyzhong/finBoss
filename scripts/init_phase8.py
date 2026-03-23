"""Phase 8 幂等初始化：users + roles + role_permissions 表及预置数据"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clickhouse_driver import Client

from api.config import get_settings


def run_ddl(client: Client):
    sql_path = os.path.join(os.path.dirname(__file__), "phase8_ddl.sql")
    with open(sql_path) as f:
        for stmt in f.read().split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                client.execute(stmt)
                print(f"  OK: {stmt[:60]}")
            except Exception as e:
                err = str(e)
                if "Code: 57" in err or "already exists" in err.lower():
                    print(f"  SKIP (exists): {stmt[:60]}")
                else:
                    raise

    # 预置角色
    roles = [
        ("finance", "财务", "AR + AP + 报表全局只读"),
        ("sales_manager", "销售经理", "AR + 报表只读（团队数据）"),
        ("ops", "运营", "预警 + 报表 + 质量读写"),
        ("admin", "系统管理员", "全部模块读写 + 系统配置"),
    ]
    for role_id, role_name, desc in roles:
        try:
            client.execute(
                "INSERT INTO dm.roles (role_id, role_name, `desc`) VALUES",
                [{"role_id": role_id, "role_name": role_name, "desc": desc}],
            )
            print(f"  INSERT role: {role_id}")
        except Exception as e:
            err = str(e)
            # ClickHouse "already exists" error codes: 57, 253
            if "57" in err or "Code: 57" in err or "Code: 253" in err or "already exists" in err.lower():
                print(f"  SKIP (exists): {stmt[:60]}")
            else:
                raise

    print("Phase 8 init complete.")


if __name__ == "__main__":
    cfg = get_settings().clickhouse
    client = Client(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
    )
    run_ddl(client)
