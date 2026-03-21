"""配置管理"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field, field_validator
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
    app_version: str = Field(default="0.2.0", description="版本号")
    api_host: str = Field(default="0.0.0.0", description="API 主机")
    api_port: int = Field(default=8000, description="API 端口")
    log_level: str = Field(default="INFO", description="日志级别")
    debug: bool = Field(default=False, description="调试模式")
    cors_origins: list[str] = Field(
        default=["http://localhost:8000", "http://127.0.0.1:8000"],
        description="CORS 允许的源列表，APP_CORS_ORIGINS 环境变量可覆盖（逗号分隔）",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        """支持字符串（逗号分隔）或列表格式"""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return v
        return ["http://localhost:8000", "http://127.0.0.1:8000"]


class OllamaConfig(BaseSettings):
    """Ollama 本地 LLM 配置"""

    model_config = SettingsConfigDict(
        env_prefix="ollama_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = Field(default="http://localhost:11434", description="Ollama 服务地址")
    model: str = Field(default="qwen2.5:7b", description="默认模型名称")
    temperature: float = Field(default=0.1, description="生成温度")
    max_tokens: int = Field(default=512, description="最大生成token数")
    timeout: int = Field(default=180, description="请求超时秒数")


class MilvusConfig(BaseSettings):
    """Milvus 向量数据库配置"""

    model_config = SettingsConfigDict(
        env_prefix="milvus_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="Milvus 主机")
    port: int = Field(default=19530, description="Milvus GRPC 端口")
    user: str = Field(default="", description="用户名")
    password: str = Field(default="", description="密码")
    collection_name: str = Field(default="finboss_knowledge", description="知识库集合名")
    embedding_model: str = Field(default="BAAI/bge-m3", description="Embedding 模型")
    top_k: int = Field(default=5, description="默认召回数量")


class FeishuConfig(BaseSettings):
    """飞书应用配置"""

    model_config = SettingsConfigDict(
        env_prefix="feishu_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_id: str = Field(default="", description="飞书应用 App ID")
    app_secret: str = Field(default="", description="飞书应用 App Secret")
    bot_name: str = Field(default="FinBoss财务助手", description="机器人名称")
    verification_token: str = Field(default="", description="Webhook 验证 Token（可选）")
    ops_channel_id: str = Field(default="", description="运营通知飞书渠道ID（群机器人或用户OpenID）")


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
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    milvus: MilvusConfig = Field(default_factory=MilvusConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)

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
