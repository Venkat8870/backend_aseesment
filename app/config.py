from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"
    simulator_base_url: str = "http://localhost:8000"


settings = Settings()



