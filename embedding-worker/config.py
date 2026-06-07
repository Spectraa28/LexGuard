from pydantic_settings import BaseSettings, SettingsConfigDict

class Setting(BaseSettings):
    # Database Configuration
    DATABASE_URL: str

    # RabbitMQ Configuration
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str
    RABBITMQ_PASS: str
    RABBITMQ_QUEUE: str

    # Cloudflare R2 Configuration
    R2_BUCKET_NAME: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_ACCOUNT_ID: str

    # Load from .env file
    model_config = SettingsConfigDict(env_file=".env", 
        extra='ignore')
    
settings = Setting()