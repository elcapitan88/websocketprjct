# app/config.py
import os
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseSettings, validator
from functools import lru_cache

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("token-refresh-config")

class TokenConfig:
    """Token refresh configuration settings"""
    # Class-level constants for global settings
    REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "120"))  # seconds
    MAX_TOKENS_PER_BATCH = int(os.getenv("MAX_TOKENS_PER_BATCH", "50"))
    ALERT_THRESHOLD = 5  # Alert after 5 failed refresh attempts

    # Broker-specific token configurations
    BROKER_TOKEN_CONFIGS = {
        'tradovate': {
            'TOKEN_LIFETIME': 4800,  # 80 minutes
            'REFRESH_THRESHOLD': 0.5625,  # Refresh at ~26.4 minutes remaining
            'MAX_RETRY_ATTEMPTS': 3,
            'RETRY_DELAY': 10,  # Seconds between retry attempts
            'SUPPORTS_REFRESH_TOKEN': False
        }
    }

    @classmethod
    def get_broker_config(cls, broker_id: str) -> dict:
        """Get token configuration for specific broker"""
        return cls.BROKER_TOKEN_CONFIGS.get(broker_id, {
            'TOKEN_LIFETIME': 4800,  # Default values if broker not found
            'REFRESH_THRESHOLD': 0.5625,
            'MAX_RETRY_ATTEMPTS': 3,
            'RETRY_DELAY': 10
        })

class Settings(BaseSettings):
    # Application settings
    SERVICE_NAME: str = "token-refresh-service"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Database settings
    DATABASE_URL: str
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30 minutes
    SQL_ECHO: bool = False
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    
    # Scheduler settings - new tiered approach
    URGENT_TIER_INTERVAL: int = int(os.getenv("URGENT_TIER_INTERVAL", "60"))  # seconds
    SOON_TIER_INTERVAL: int = int(os.getenv("SOON_TIER_INTERVAL", "300"))  # seconds (5 minutes)
    NORMAL_TIER_INTERVAL: int = int(os.getenv("NORMAL_TIER_INTERVAL", "1800"))  # seconds (30 minutes)
    
    # Worker settings from your original implementation
    WORKER_SLEEP_INTERVAL: int = int(os.getenv("WORKER_SLEEP_INTERVAL", "10"))  # seconds
    LOCK_TIMEOUT: int = int(os.getenv("LOCK_TIMEOUT", "30"))  # seconds
    
    # Token refresh settings
    MAX_REFRESH_ATTEMPTS: int = int(os.getenv("MAX_REFRESH_ATTEMPTS", "3"))
    REFRESH_BATCH_SIZE: int = int(os.getenv("REFRESH_BATCH_SIZE", "10"))
    
    # Broker-specific settings
    TRADOVATE_CLIENT_ID: Optional[str] = os.getenv("TRADOVATE_CLIENT_ID", "")
    TRADOVATE_CLIENT_SECRET: Optional[str] = os.getenv("TRADOVATE_CLIENT_SECRET", "")
    TRADOVATE_LIVE_RENEW_TOKEN_URL: Optional[str] = os.getenv("TRADOVATE_LIVE_RENEW_TOKEN_URL", "")
    TRADOVATE_DEMO_RENEW_TOKEN_URL: Optional[str] = os.getenv("TRADOVATE_DEMO_RENEW_TOKEN_URL", "")
    
    # Monitoring settings
    HEALTH_CHECK_INTERVAL: int = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))  # seconds
    STATUS_UPDATE_INTERVAL: int = int(os.getenv("STATUS_UPDATE_INTERVAL", "300"))  # seconds (5 minutes)
    
    # Validation
    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        if not v:
            raise ValueError("DATABASE_URL environment variable is required")
        return v

    @validator("SECRET_KEY")
    def validate_secret_key(cls, v, values):
        if not v:
            logger.warning("SECRET_KEY not set, using a random value")
            return os.urandom(32).hex()
        return v
    
    def _validate_settings(self):
        """Additional validation for backward compatibility"""
        if self.ENVIRONMENT == "production":
            if not self.TRADOVATE_CLIENT_ID or not self.TRADOVATE_CLIENT_SECRET:
                logger.warning("Tradovate credentials not configured in production environment")
            
            if not self.TRADOVATE_LIVE_RENEW_TOKEN_URL or not self.TRADOVATE_DEMO_RENEW_TOKEN_URL:
                logger.warning("Tradovate renew token URLs not configured in production environment")
    
    # Meta configuration
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    # Helper methods
    def get_db_params(self) -> Dict[str, Any]:
        """Get database connection parameters"""
        return {
            "pool_size": self.DB_POOL_SIZE,
            "max_overflow": self.DB_MAX_OVERFLOW,
            "pool_timeout": self.DB_POOL_TIMEOUT,
            "pool_recycle": self.DB_POOL_RECYCLE,
            "pool_pre_ping": True,
            "echo": self.SQL_ECHO,
        }
    
    def is_production(self) -> bool:
        """Check if environment is production"""
        return self.ENVIRONMENT.lower() == "production"
    
    def get_broker_urls(self, broker_id: str, environment: str) -> Dict[str, str]:
        """Get broker-specific URLs based on environment"""
        if broker_id.lower() == "tradovate":
            if environment.lower() == "live":
                return {
                    "renew_token_url": self.TRADOVATE_LIVE_RENEW_TOKEN_URL
                }
            else:  # demo is default
                return {
                    "renew_token_url": self.TRADOVATE_DEMO_RENEW_TOKEN_URL
                }
        return {}
    
    def get_broker_config(self, broker_id: str) -> Dict[str, Any]:
        """Get broker-specific configuration"""
        if broker_id == "tradovate":
            return {
                "client_id": self.TRADOVATE_CLIENT_ID,
                "client_secret": self.TRADOVATE_CLIENT_SECRET,
                "live_renew_token_url": self.TRADOVATE_LIVE_RENEW_TOKEN_URL,
                "demo_renew_token_url": self.TRADOVATE_DEMO_RENEW_TOKEN_URL,
                "token_lifetime": 4800,  # 80 minutes (Tradovate token lifetime)
                "refresh_threshold": 0.5625,  # Refresh at ~45 minutes
                "max_retry_attempts": self.MAX_REFRESH_ATTEMPTS,
            }
        # Add other brokers here as needed
        return {}


@lru_cache()
def get_settings() -> Settings:
    """
    Create and cache settings instance.
    Using lru_cache ensures settings are only loaded once.
    """
    logger.info("Loading application settings")
    settings = Settings()
    settings._validate_settings()  # Run additional validation
    return settings


# Create settings instance
settings = get_settings()

# If needed for backward compatibility
token_config = TokenConfig()

# Perform validation on startup
if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")