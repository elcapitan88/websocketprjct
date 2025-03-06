import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from ..config import settings

def setup_logging() -> logging.Logger:
    """
    Configure logging for the application
    
    Returns:
        Logger instance for the main application
    """
    # Get log level from settings
    log_level_name = settings.LOG_LEVEL.upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    
    # Basic configuration
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    
    # Create logger
    logger = logging.getLogger("token_refresh_service")
    logger.setLevel(log_level)
    
    # Clear existing handlers to avoid duplication
    if logger.handlers:
        logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler if in production or specifically enabled
    if settings.ENVIRONMENT == "production" or os.environ.get("ENABLE_FILE_LOGGING") == "true":
        log_dir = os.environ.get("LOG_DIR", "./logs")
        
        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Rotating file handler (10MB max, keep 5 backups)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "token_service.log"),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        
        file_formatter = logging.Formatter(
            '%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Set log levels for third-party libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    logger.info(f"Logging configured with level {log_level_name}")
    
    return logger

# Function to get a logger for a specific module
def get_module_logger(module_name: str) -> logging.Logger:
    """
    Get a logger for a specific module
    
    Args:
        module_name: Name of the module
        
    Returns:
        Logger instance for the specified module
    """
    return logging.getLogger(f"token_refresh_service.{module_name}")