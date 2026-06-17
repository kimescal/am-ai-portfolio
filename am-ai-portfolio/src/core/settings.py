import logging
import os
from enum import StrEnum
from json import loads
from typing import Annotated

from dotenv import find_dotenv
from pydantic import (
    BeforeValidator,
    Field,
    HttpUrl,
    SecretStr,
    TypeAdapter,
    computed_field,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseType(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MONGO = "mongo"


def check_str_is_http(x: str) -> str:
    http_url_adapter = TypeAdapter(HttpUrl)
    return str(http_url_adapter.validate_python(x))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_default=False,
    )
    MODE: str | None = None

    HOST: str = "0.0.0.0"
    PORT: int = 8080

    AUTH_SECRET: SecretStr | None = None

    # If DEFAULT_MODEL is None, it will be set in model_post_init
    AVAILABLE_MODELS: set[str] = set(["qwen3-32b", "citics-r1-local", "deepseek-v3", "citics-large", "qwen3-235b"])  # type: ignore[assignment]
    DEFAULT_MODEL: str | None = "qwen3-32b"  # type: ignore[assignment]
    COMPATIBLE_API_KEY: SecretStr | None = None
    COMPATIBLE_BASE_URL: str | None = None

    DEFAULT_AGENT: str = "chatbot"

    LANGFUSE_TRACING: bool = False
    LANGFUSE_HOST: Annotated[str, BeforeValidator(check_str_is_http)] = "https://cloud.langfuse.com"
    LANGFUSE_PUBLIC_KEY: SecretStr | None = None
    LANGFUSE_SECRET_KEY: SecretStr | None = None

    # Database Configuration
    DATABASE_TYPE: DatabaseType = (
        DatabaseType.SQLITE
    )  # Options: DatabaseType.SQLITE or DatabaseType.POSTGRES
    SQLITE_DB_PATH: str = "db/checkpoints.db"

    # PostgreSQL Configuration
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: SecretStr | None = None
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_APPLICATION_NAME: str = "agent-service-toolkit"
    POSTGRES_MIN_CONNECTIONS_PER_POOL: int = 1
    POSTGRES_MAX_CONNECTIONS_PER_POOL: int = 1

    # MongoDB Configuration
    MONGO_HOST: str | None = None
    MONGO_PORT: int | None = None
    MONGO_DB: str | None = None
    MONGO_USER: str | None = None
    MONGO_PASSWORD: SecretStr | None = None
    MONGO_AUTH_SOURCE: str | None = None

    # OceanBase Configuration
    OCEANBASE_ENABLED: bool = False
    OCEANBASE_HOST: str | None = None
    OCEANBASE_PORT: int | None = None
    OCEANBASE_USER: str | None = None
    OCEANBASE_PASSWORD: SecretStr | None = None
    OCEANBASE_DB: str | None = None

    # qiwei Settings
    QIWEI_TOKEN: SecretStr | None = None
    QIWEI_ENCODING_AES_KEY: SecretStr | None = None
    QIWEI_CORP_ID: str | None = ""

    UVICORN_WORKERS: int | None = None

    # qiwei welcome card config
    QIWEI_WELCOME_TEMPALTE: str | None = None

    WEB_URL: str | None = None

    # 从环境变量加载的RAG配置
    RAG_URL: str | None = None
    RAG_API_KEYS: SecretStr | None = None
    
    # History Manager Configuration
    HISTORY_MAX_TOKENS: int = 1000000
    HISTORY_SUMMARY_MODEL: str | None = "qwen-plus-latest"
    
    # AMCELL service configuration
    AMCELL_ADDR: str | None = None

    # 资管战略客户AI接口服务地址
    PROFILE_ADDR: str | None = None
    PROFILE_API_URL: str | None = None
    PROFILE_USER_CODE: str | None = None
    PROFILE_PASSWORD: SecretStr | None = None
    PROFILE_TOKEN_TTL: int = 43200

    # API Configuration for Dynamic Report Job
    QIWEI_PUSH_API_URL: str | None = None
    QIWEI_PUSH_API_LOGIN_USERCODE: str | None = None
    QIWEI_PUSH_API_LOGIN_PASSWORD: str | None = None
    QIWEI_PUSH_API_SENDTEXT_AGENTID: str | None = None

    # SQL Query Permission Control Configuration
    # FORMAT: dict[str, dict[str, bool]] - table_name -> {permission_field: is_list_field}
    # where is_list_field indicates if the database field contains comma-separated values
    SQL_PERMISSION_TABLE_FIELDS: dict[str, dict[str, bool]] = None

    # Visit Rate Analysis Permission Control
    # FORMAT: comma-separated user IDs
    VISIT_RATE_ANALYSIS: str | None = None

    # Visit Whitelist - for intent_guard permission check
    # FORMAT: comma-separated Chinese names
    VISIT_WHITELIST_NAMES: str | None = None

    # File Sending Control
    SEND_FILE_FLAG: bool = False

    HIDE_TOOL_NAMES: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def VISIT_RATE_ANALYSIS_USERS(self) -> list[str]:
        """获取有权限查看拜访率分析的用户 ID 列表"""
        if not self.VISIT_RATE_ANALYSIS:
            return []
        return [user_id.strip() for user_id in self.VISIT_RATE_ANALYSIS.split(",")]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def VISIT_WHITELIST_NAMES_LIST(self) -> list[str]:
        """获取访问白名单用户姓名列表"""
        if not self.VISIT_WHITELIST_NAMES:
            return []
        return [name.strip() for name in self.VISIT_WHITELIST_NAMES.split(",")]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def HIDE_TOOL_NAMES_LIST(self) -> list[str]:
        """获取需要隐藏的工具名称列表"""
        if not self.HIDE_TOOL_NAMES:
            return []
        return [tool_name.strip() for tool_name in self.HIDE_TOOL_NAMES.split(",")]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def BASE_URL(self) -> str:
        return f"http://{self.HOST}:{self.PORT}"

    def is_dev(self) -> bool:
        return self.MODE == "dev"

    def get_sql_syntax(self) -> str:
        """Get the appropriate SQL syntax based on the current environment mode."""
        return "mysql" if self.OCEANBASE_ENABLED else "pandasql"

    def get_rag_config(self, db_name: str) -> dict:
        api_keys = loads(self.RAG_API_KEYS.get_secret_value()) 
        return {"url": self.RAG_URL, "api_key": SecretStr(api_keys[db_name.upper()])}

settings = Settings()
