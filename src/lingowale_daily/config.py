"""配置：从环境变量读取，缺值即报错。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # PostHog
    posthog_host: str = "https://us.posthog.com"
    posthog_project_id: str
    posthog_api_key: str

    # 飞书自建应用
    feishu_app_id: str
    feishu_app_secret: str
    feishu_target_chat_id: str

    # 飞书告警 webhook（独立于 app token，兜底告警用）
    feishu_alert_webhook: str
    feishu_alert_secret: str = ""

    # AI 分析（可选）
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
