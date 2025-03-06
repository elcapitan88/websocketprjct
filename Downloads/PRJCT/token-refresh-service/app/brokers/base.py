from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class BrokerException(Exception):
    """Base exception for broker-related errors"""
    pass

class TokenRefreshException(BrokerException):
    """Exception raised when token refresh fails"""
    pass

class BaseBroker(ABC):
    """
    Base class for broker-specific token refresh implementations.
    Each broker implementation must extend this class and implement
    the required methods.
    """
    
    def __init__(self, broker_id: str, environment: str):
        """
        Initialize the broker implementation
        
        Args:
            broker_id: Broker identifier (e.g., 'tradovate')
            environment: Environment identifier (e.g., 'demo', 'live')
        """
        self.broker_id = broker_id
        self.environment = environment
        self.logger = logging.getLogger(f"token_refresh_service.broker.{broker_id}")
        self.logger.info(f"Initialized {broker_id} broker for {environment} environment")
    
    @abstractmethod
    async def refresh_token(self, credential: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Refresh an access token for this broker
        
        Args:
            credential: Dictionary containing credential information
            db: Database session for persistence
            
        Returns:
            Updated credential information
            
        Raises:
            TokenRefreshException: If token refresh fails
        """
        pass
    
    @abstractmethod
    async def validate_token(self, credential: Dict[str, Any]) -> bool:
        """
        Validate if a token is still valid
        
        Args:
            credential: Dictionary containing credential information
            
        Returns:
            True if token is valid, False otherwise
        """
        pass
    
    @staticmethod
    def get_broker_instance(broker_id: str, environment: str) -> 'BaseBroker':
        """
        Factory method to get the appropriate broker implementation
        
        Args:
            broker_id: Broker identifier (e.g., 'tradovate')
            environment: Environment identifier (e.g., 'demo', 'live')
            
        Returns:
            Broker implementation instance
            
        Raises:
            ValueError: If broker_id is not supported
        """
        from .implementations.tradovate import TradovateBroker
        
        broker_map = {
            "tradovate": TradovateBroker
        }
        
        if broker_id.lower() not in broker_map:
            raise ValueError(f"Unsupported broker: {broker_id}")
        
        return broker_map[broker_id.lower()](broker_id, environment)