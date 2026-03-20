"""配置管理"""
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KingdeeDBConfig(BaseSettings):
    """金蝶数据库配置"""

    model_config = SettingsConfigDict(
        env_prefix="kingdee_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="数据库主机")
    port: int = Field(default=1433, description="数据库端口")
    name: str = Field(default="AIS20220323153128", description="数据库名称")
    user: str = Field(default="sa", description="用户名")
    password: str = Field(default="", description="密码")

    @property
    def jdbc_url(self) -> str:
        return f"jdbc:jtds:sqlserver://{self.host}:{self.port};databaseName={self.name}"


class MinioConfig(BaseSettings):
    """MinIO 配置"""

    model_config = SettingsConfigDict(
        env_prefix="minio_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoint: str = Field(default="localhost:9000", description="MinIO endpoint")
    access_key: str = Field(default="minioadmin", description="Access Key")
    secret_key: str = Field(default="minioadmin", description="Secret Key")
    bucket: str = Field(default="finboss", description="Bucket名称")


class DorisConfig(BaseSettings):
    """Doris 配置"""

    model_config = SettingsConfigDict(
        env_prefix="doris_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="Doris FE 主机")
    port: int = Field(default=9030, description="Doris FE 端口")
    user: str = Field(default="root", description="用户名")
    password: str = Field(default="", description="密码")

    @property
    def connection_url(self) -> str:
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}"


class ClickHouseConfig(BaseSettings):
    """ClickHouse 配置"""

    model_config = SettingsConfigDict(
        env_prefix="clickhouse_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="ClickHouse 主机")
    port: int = Field(default=9000, description="ClickHouse 端口")
    user: str = Field(default="default", description="用户名")
    password: str = Field(default="", description="密码")
    database: str = Field(default="finboss", description="数据库名")


class IcebergConfig(BaseSettings):
    """Iceberg 配置"""

    model_config = SettingsConfigDict(
        env_prefix="iceberg_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    warehouse: str = Field(default="s3://finboss/warehouse", description="仓库路径")
    catalog_uri: str = Field(default="http://localhost:19120/api/v1", description="Catalog URI")


class AppConfig(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_prefix="app_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="FinBoss", description="应用名称")
    app_version: str = Field(default="0.1.0", description="版本号")
    api_host: str = Field(default="0.0.0.0", description="API 主机")
    api_port: int = Field(default=8000, description="API 端口")
    log_level: str = Field(default="INFO", description="日志级别")
    debug: bool = Field(default=False, description="调试模式")


class Settings(BaseSettings):
    """全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略环境变量中额外字段
    )

    kingdee: KingdeeDBConfig = Field(default_factory=KingdeeDBConfig)
    minio: MinioConfig = Field(default_factory=MinioConfig)
    doris: DorisConfig = Field(default_factory=DorisConfig)
    clickhouse: ClickHouseConfig = Field(default_factory=ClickHouseConfig)
    iceberg: IcebergConfig = Field(default_factory=IcebergConfig)
    app: AppConfig = Field(default_factory=AppConfig)

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> "Settings":
        """从 YAML 文件加载配置"""
        config_path = Path(config_path)
        if not config_path.exists():
            return cls()
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)


@lru_cache
def get_settings() -> Settings:
    """获取全局配置实例"""
    return Settings()
