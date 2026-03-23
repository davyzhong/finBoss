"""Admin routes for user and role management."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["系统管理"])


def _require_admin(request: Request) -> dict:
    """Require the current user to be an admin, otherwise raise 403."""
    user = getattr(request.state, "user", None) if hasattr(request, "state") else None
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


class UpdateRoleRequest(BaseModel):
    """Request body for updating a user's role."""
    role: str


@router.get("/roles")
async def list_roles(request: Request):
    """List all available roles."""
    _require_admin(request)
    svc = UserService()
    return {"roles": svc.list_roles()}


@router.get("/users")
async def list_users(request: Request):
    """List all users (up to 100, ordered by creation date)."""
    _require_admin(request)
    svc = UserService()
    return {"users": svc.list_users()}


@router.put("/users/{user_id}/role")
async def update_user_role(request: Request, user_id: str, body: UpdateRoleRequest):
    """Update the role for a specific user."""
    _require_admin(request)
    svc = UserService()
    svc.update_user_role(user_id, body.role)
    return {"success": True, "user_id": user_id, "role": body.role}
