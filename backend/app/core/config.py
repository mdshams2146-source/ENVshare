from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'envshare.db'}"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    APP_ENCRYPTION_KEY: str
    RESET_TOKEN_SECRET: str = ""
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"

    class Config:
        env_file = str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else ".env"
        extra = "ignore"

settings = Settings()
