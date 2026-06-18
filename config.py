# -*- coding: utf-8 -*-
"""
微舆配置文件

此模块使用 pydantic-settings 管理全局配置，支持从环境变量和 .env 文件自动加载。
数据模型定义位置：
- 本文件 - 配置模型定义
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict, field_validator
from typing import Optional, Literal
from loguru import logger


# 计算 .env 优先级：优先当前工作目录，其次项目根目录
PROJECT_ROOT: Path = Path(__file__).resolve().parent
CWD_ENV: Path = Path.cwd() / ".env"
ENV_FILE: str = str(CWD_ENV if CWD_ENV.exists() else (PROJECT_ROOT / ".env"))
DEFAULT_SECRET_KEY = "bettafish-local-dev-secret"


class Settings(BaseSettings):
    """
    全局配置；支持 .env 和环境变量自动加载。
    变量名与原 config.py 大写一致，便于平滑过渡。
    """
    # ================== Flask 服务器配置 ====================
    HOST: str = Field("0.0.0.0", description="BETTAFISH 主机地址，例如 0.0.0.0 或 127.0.0.1")
    PORT: int = Field(5000, description="Flask服务器端口号，默认5000")
    SECRET_KEY: str = Field(DEFAULT_SECRET_KEY, description="Flask session signing secret; override in .env for shared or deployed environments")

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def default_blank_secret_key(cls, value: object) -> object:
        if value is None:
            return DEFAULT_SECRET_KEY
        if isinstance(value, str) and not value.strip():
            return DEFAULT_SECRET_KEY
        return value

    # ====================== 数据库配置 ======================
    DB_DIALECT: str = Field("postgresql", description="数据库类型，可选 mysql 或 postgresql；请与其他连接信息同时配置")
    DB_HOST: str = Field("your_db_host", description="数据库主机，例如localhost 或 127.0.0.1")
    DB_PORT: int = Field(5432, description="数据库端口号，postgresql默认为5432，mysql默认为3306")
    DB_USER: str = Field("your_db_user", description="数据库用户名")
    DB_PASSWORD: str = Field("your_db_password", description="数据库密码")
    DB_NAME: str = Field("your_db_name", description="数据库名称")
    DB_CHARSET: str = Field("utf8mb4", description="数据库字符集，推荐utf8mb4，兼容emoji")
    
    # ======================= LLM 相关 =======================
    # Insight Agent（推荐Kimi，申请地址：https://platform.moonshot.cn/）
    INSIGHT_ENGINE_API_KEY: Optional[str] = Field(None, description="Insight Agent（推荐 kimi-k2，官方申请地址：https://platform.moonshot.cn/）API 密钥，用于主 LLM。🚩请先按推荐配置申请并跑通，再根据需要调整 KEY、BASE_URL 与 MODEL_NAME。")
    INSIGHT_ENGINE_BASE_URL: Optional[str] = Field("https://api.moonshot.cn/v1", description="Insight Agent LLM BaseUrl，可根据厂商自定义")
    INSIGHT_ENGINE_MODEL_NAME: str = Field("kimi-k2-0711-preview", description="Insight Agent LLM 模型名称，例如 kimi-k2-0711-preview")
    
    # Media Agent（推荐使用具备较强中文长文能力的 OpenAI-compatible 模型）
    MEDIA_ENGINE_API_KEY: Optional[str] = Field(None, description="Media Agent LLM API 密钥")
    MEDIA_ENGINE_BASE_URL: Optional[str] = Field("", description="Media Agent LLM BaseUrl，可根据中转服务调整")
    MEDIA_ENGINE_MODEL_NAME: str = Field("gemini-2.5-pro", description="Media Agent LLM 模型名称，如 gemini-2.5-pro")
    
    # Query Agent（推荐DeepSeek，申请地址：https://www.deepseek.com/）
    QUERY_ENGINE_API_KEY: Optional[str] = Field(None, description="Query Agent（推荐 deepseek，官方申请地址：https://platform.deepseek.com/）API 密钥")
    QUERY_ENGINE_BASE_URL: Optional[str] = Field("https://api.deepseek.com", description="Query Agent LLM BaseUrl")
    QUERY_ENGINE_MODEL_NAME: str = Field("deepseek-chat", description="Query Agent LLM 模型名称，如 deepseek-reasoner")
    
    # Report Agent（推荐使用具备较强中文长文能力的 OpenAI-compatible 模型）
    REPORT_ENGINE_API_KEY: Optional[str] = Field(None, description="Report Agent LLM API 密钥")
    REPORT_ENGINE_BASE_URL: Optional[str] = Field("", description="Report Agent LLM BaseUrl，可根据中转服务调整")
    REPORT_ENGINE_MODEL_NAME: str = Field("gemini-2.5-pro", description="Report Agent LLM 模型名称，如 gemini-2.5-pro")

    # Optional legacy crawler agent settings. Leave blank unless an external compatible crawler integration is provided.
    MINDSPIDER_API_KEY: Optional[str] = Field(None, description="Optional external crawler agent API key")
    MINDSPIDER_BASE_URL: Optional[str] = Field(None, description="Optional external crawler agent base URL")
    MINDSPIDER_MODEL_NAME: Optional[str] = Field(None, description="Optional external crawler agent model name")
    
    # Forum Host（Qwen3最新模型，这里我使用了硅基流动这个平台，申请地址：https://cloud.siliconflow.cn/）
    FORUM_HOST_API_KEY: Optional[str] = Field(None, description="Forum Host（推荐 qwen-plus，官方申请地址：https://www.aliyun.com/product/bailian）API 密钥")
    FORUM_HOST_BASE_URL: Optional[str] = Field(None, description="Forum Host LLM BaseUrl，可按所选服务配置")
    FORUM_HOST_MODEL_NAME: Optional[str] = Field(None, description="Forum Host LLM 模型名称，例如 qwen-plus")
    
    # SQL keyword Optimizer（小参数Qwen3模型，这里我使用了硅基流动这个平台，申请地址：https://cloud.siliconflow.cn/）
    KEYWORD_OPTIMIZER_API_KEY: Optional[str] = Field(None, description="SQL Keyword Optimizer（推荐 qwen-plus，官方申请地址：https://www.aliyun.com/product/bailian）API 密钥")
    KEYWORD_OPTIMIZER_BASE_URL: Optional[str] = Field(None, description="Keyword Optimizer BaseUrl，可按所选服务配置")
    KEYWORD_OPTIMIZER_MODEL_NAME: Optional[str] = Field(None, description="Keyword Optimizer LLM 模型名称，例如 qwen-plus")
    
    # ================== 网络工具配置 ====================
    # Tavily API（申请地址：https://www.tavily.com/）
    TAVILY_API_KEY: Optional[str] = Field(None, description="Tavily API（申请地址：https://www.tavily.com/）API密钥，用于Tavily网络搜索")

    SEARCH_TOOL_TYPE: Literal["AnspireAPI", "BochaAPI", "TavilyAPI"] = Field("AnspireAPI", description="网络搜索工具类型，支持BochaAPI、AnspireAPI或TavilyAPI，默认为AnspireAPI")
    # Bocha API（申请地址：https://open.bochaai.com/）
    BOCHA_BASE_URL: Optional[str] = Field("https://api.bocha.cn/v1/web-search", description="Bocha Web Search BaseUrl")
    BOCHA_WEB_SEARCH_API_KEY: Optional[str] = Field(None, description="Bocha API（申请地址：https://open.bochaai.com/）API密钥，用于Bocha搜索")

    # Anspire AI Search API
    ANSPIRE_BASE_URL: Optional[str] = Field("https://plugin.anspire.cn/api/ntsearch/search", description="Anspire AI 搜索BaseUrl")
    ANSPIRE_API_KEY: Optional[str] = Field(None, description="Anspire AI Search APIAPI密钥，用于Anspire搜索")

    INTAKE_WEB_SEARCH_DEFAULT_RESULTS: int = Field(
        5,
        description="Default result count for lightweight intake web search",
    )
    INTAKE_WEB_SEARCH_MAX_RESULTS: int = Field(
        8,
        description="Hard result cap for lightweight intake web search",
    )
    ARGUS_SEARCH_ENGINE_TIMEOUT_SECONDS: int = Field(
        5400,
        description="Maximum runtime for each Argus search engine before surfacing a clear failure; <=0 disables",
    )
    ARGUS_SEARCH_ENGINE_CONCURRENCY: Literal["sequential", "concurrent"] = Field(
        "sequential",
        description="Run restored Argus engines sequentially for stable local MVP smokes, or concurrently for faster high-resource environments",
    )
    ARGUS_SEARCH_ENGINE_MAX_REFLECTIONS: int = Field(
        1,
        description="Default reflection rounds per local Argus engine run",
    )
    ARGUS_SEARCH_ENGINE_MAX_PARAGRAPHS: int = Field(
        5,
        description="Maximum report-structure paragraphs each local Argus engine should process",
    )
    ARGUS_INSIGHT_MAX_AUTO_SENTIMENT_SEARCHES: int = Field(
        1,
        description="Maximum automatic sentiment-analysis search batches per InsightEngine run; <=0 disables the cap",
    )

    # ================== SaaS crawler bridge ====================
    CRAWLER_CLOUD_ENDPOINT: Optional[str] = Field(None, description="Optional cloud MediaCrawler job endpoint for SaaS crawl-prep tasks")
    CRAWLER_CLOUD_API_KEY: Optional[str] = Field(None, description="Optional bearer token for CRAWLER_CLOUD_ENDPOINT")
    CRAWLER_CLOUD_TIMEOUT: int = Field(10, description="Cloud crawler job submission timeout in seconds")

    # ================== Weibo data prep provider ====================
    WEIBO_DATA_PROVIDER: Literal["mediacrawler", "tikhub"] = Field(
        "tikhub",
        description="Weibo data prep provider, defaulting to TikHub SDK for the MVP",
    )
    WEIBO_DATA_SEARCH_PAGES_PER_KEYWORD: int = Field(
        3,
        description="TikHub Weibo search pages per keyword",
    )
    WEIBO_DATA_SEARCH_TYPE: str = Field(
        "61",
        description="TikHub Weibo search_type for data prep",
    )
    WEIBO_DATA_MAX_KEYWORDS: int = Field(6, description="Maximum keywords used by Weibo data prep")
    WEIBO_DATA_MAX_POSTS_PER_KEYWORD: int = Field(
        30,
        description="Maximum candidate posts collected per keyword",
    )
    WEIBO_DATA_MAX_SELECTED_POSTS: int = Field(
        12,
        description="Maximum posts selected for comment expansion",
    )
    WEIBO_DATA_MAX_COMMENTS_PER_POST: int = Field(
        20,
        description="Target number of first-level comments per selected post",
    )
    WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD: int = Field(
        30,
        description="Hard cap of first-level comments per selected post",
    )
    WEIBO_DATA_ALLOW_SUBCOMMENTS: bool = Field(
        False,
        description="Whether Weibo data prep should fetch second-level comments",
    )
    TIKHUB_BASE_URL: Optional[str] = Field(
        None,
        description="Optional TikHub SDK/API base URL for Weibo data prep",
    )
    TIKHUB_API_KEY: Optional[str] = Field(
        None,
        description="Optional TikHub API key for Weibo data prep",
    )
    TIKHUB_TIMEOUT: int = Field(
        10,
        description="TikHub request timeout in seconds",
    )

    
    # ================== Insight Engine 搜索配置 ====================
    DEFAULT_SEARCH_HOT_CONTENT_LIMIT: int = Field(100, description="热榜内容默认最大数")
    DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE: int = Field(50, description="按表全局话题最大数")
    DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE: int = Field(100, description="按日期话题最大数")
    DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT: int = Field(500, description="单话题评论最大数")
    DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT: int = Field(200, description="平台搜索话题最大数")
    MAX_SEARCH_RESULTS_FOR_LLM: int = Field(0, description="供LLM用搜索结果最大数")
    MAX_HIGH_CONFIDENCE_SENTIMENT_RESULTS: int = Field(0, description="高置信度情感分析最大数")
    KEYWORD_OPTIMIZER_MAX_KEYWORDS: int = Field(8, description="关键词优化器返回关键词最大数量")
    MAX_REFLECTIONS: int = Field(3, description="最大反思次数")
    MAX_PARAGRAPHS: int = Field(6, description="最大段落数")
    SEARCH_TIMEOUT: int = Field(240, description="单次搜索请求超时")
    MAX_CONTENT_LENGTH: int = Field(500000, description="搜索最大内容长度")
    
    model_config = ConfigDict(
        env_file=ENV_FILE,
        env_prefix="",
        case_sensitive=False,
        extra="allow"
    )


# 创建全局配置实例
settings = Settings()


def reload_settings() -> Settings:
    """
    重新加载配置
    
    从 .env 文件和环境变量重新加载配置，更新全局 settings 实例。
    用于在运行时动态更新配置。
    
    Returns:
        Settings: 新创建的配置实例
    """
    
    global settings
    settings = Settings()
    return settings
