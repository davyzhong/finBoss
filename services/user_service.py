"""User management service for admin operations."""
from datetime import datetime
from typing import Any

from services.clickhouse_service import ClickHouseDataService


class UserService:
    """Service for managing users and roles via ClickHouse."""

    def list_users(self) -> list[dict[str, Any]]:
        """Return up to 100 users ordered by creation date descending."""
        ch = ClickHouseDataService()
        rows = ch.execute_query(
            "SELECT user_id, external_id, provider, name, email, role, is_active, created_at "
            "FROM dm.users ORDER BY created_at DESC LIMIT 100"
        )
        return [
            {
                "user_id": r["user_id"],
                "external_id": r["external_id"],
                "provider": r["provider"],
                "name": r["name"],
                "email": r["email"],
                "role": r["role"],
                "is_active": bool(r["is_active"]),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
            }
            for r in rows
        ]

    def update_user_role(self, user_id: str, role: str) -> bool:
        """Update the role for a given user. Returns True."""
        ch = ClickHouseDataService()
        ch.client.execute(
            "ALTER TABLE dm.users UPDATE role = %(role)s, updated_at = %(now)s WHERE user_id = %(uid)s",
            {"uid": user_id, "role": role, "now": datetime.utcnow()},
        )
        return True

    def list_roles(self) -> list[dict[str, str]]:
        """Return all available roles."""
        ch = ClickHouseDataService()
        rows = ch.execute_query(
            "SELECT role_id, role_name, desc FROM dm.roles ORDER BY role_id"
        )
        return [
            {"role_id": r["role_id"], "role_name": r["role_name"], "desc": r["desc"] or ""}
            for r in rows
        ]
