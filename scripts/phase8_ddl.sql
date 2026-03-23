-- Phase 8: Users + RBAC Schema

-- 用户表
CREATE TABLE IF NOT EXISTS dm.users (
    user_id     String,
    external_id String,
    provider    String,
    name        String,
    email       String,
    role        String DEFAULT '',
    is_active   UInt8  DEFAULT 1,
    created_at  DateTime DEFAULT now(),
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY user_id;

-- 角色表
CREATE TABLE IF NOT EXISTS dm.roles (
    role_id     String,
    role_name   String,
    desc        String DEFAULT '',
    created_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY role_id;

-- 角色权限矩阵
CREATE TABLE IF NOT EXISTS dm.role_permissions (
    role_id     String,
    module      String,
    can_read    UInt8 DEFAULT 0,
    can_write   UInt8 DEFAULT 0,
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (role_id, module);
