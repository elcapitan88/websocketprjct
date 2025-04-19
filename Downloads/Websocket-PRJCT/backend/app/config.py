from pydantic_settings import BaseSettings
from typing import List
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # Tradovate OAuth Config
    TRADOVATE_CLIENT_ID: str = os.getenv("TRADOVATE_CLIENT_ID", "5922")
    TRADOVATE_CLIENT_SECRET: str = os.getenv("TRADOVATE_CLIENT_SECRET", "a8cc68f5-27e9-41a2-afa5-6c9d376da8a7")
    TRADOVATE_REDIRECT_URI: str = os.getenv("TRADOVATE_REDIRECT_URI", "http://localhost:3000/callback")
    
    # API Endpoints
    TRADOVATE_AUTH_URL: str = os.getenv("TRADOVATE_AUTH_URL", "https://live.tradovateapi.com/auth/oauth/authorize")
    TRADOVATE_TOKEN_URL: str = os.getenv("TRADOVATE_TOKEN_URL", "https://live.tradovateapi.com/auth/oauth/token")
    TRADOVATE_API_URL: str = os.getenv("TRADOVATE_API_URL", "https://live.tradovateapi.com/v1")
    TRADOVATE_WS_URL: str = os.getenv("TRADOVATE_WS_URL", "wss://live.tradovateapi.com/v1/websocket")
    
    # Application Config
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-for-jwt-generation")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Server Config
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5000"]
    
    class Config:
        case_sensitive = True

# Create a settings instance
settings = Settings()