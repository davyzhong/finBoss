from datetime import datetime
from pydantic import BaseModel, Field


class User(BaseModel):
    user_id: str = Field(description="本地用户ID（UUID）")
    external_id: str = Field(description="IdP 的 union_id / user_id")
    provider: str = Field(description="feishu | dingtalk | wecom")
    name: str = Field(default="")
    email: str = Field(default="")
    role: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Role(BaseModel):
    role_id: str = Field(description="角色ID")
    role_name: str = Field(description="角色名")
    desc: str = Field(default="", description="描述")


class RolePermission(BaseModel):
    role_id: str = Field(description="角色ID")
    module: str = Field(description="模块名（ar/ap/reports/alerts/quality/admin）")
    can_read: bool = Field(default=False)
    can_write: bool = Field(default=False)
