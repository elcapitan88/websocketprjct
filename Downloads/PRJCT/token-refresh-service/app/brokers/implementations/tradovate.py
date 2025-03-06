import httpx
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..base import BaseBroker, TokenRefreshException
from ...config import settings, token_config

logger = logging.getLogger(__name__)

class TradovateBroker(BaseBroker):
    """
    Implementation of token refresh for Tradovate broker
    """
    
    def __init__(self, broker_id: str, environment: str):
        """
        Initialize Tradovate broker
        
        Args:
            broker_id: Expected to be 'tradovate'
            environment: 'demo' or 'live'
        """
        super().__init__(broker_id, environment)
        self.client = httpx.AsyncClient(timeout=30.0)
        self.broker_config = token_config.get_broker_config(broker_id)
        
        # Get environment-specific URLs
        broker_urls = settings.get_broker_urls(broker_id, environment)
        self.renew_token_url = broker_urls.get('renew_token_url')
        
        if not self.renew_token_url:
            raise ValueError(f"Missing renew token URL for Tradovate {environment} environment")
        
        logger.info(f"Initialized Tradovate broker for {environment} environment")
    
    async def close(self):
        """Close resources"""
        await self.client.aclose()
    
    async def refresh_token(self, credential: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Refresh Tradovate access token
        
        Args:
            credential: Dictionary containing credential information
            db: Database session for persistence
            
        Returns:
            Updated credential information
            
        Raises:
            TokenRefreshException: If token refresh fails
        """
        try:
            # Extract access token from credential
            access_token = credential.get('access_token')
            if not access_token:
                raise TokenRefreshException("Missing access token in credential")
            
            # Prepare headers with existing token
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}'
            }
            
            # Make token renewal request
            logger.debug(f"Sending token refresh request to {self.renew_token_url}")
            response = await self.client.post(
                self.renew_token_url,
                headers=headers
            )
            
            # Check for successful response
            if response.status_code != 200:
                raise TokenRefreshException(
                    f"Token refresh failed with status {response.status_code}: {response.text}"
                )
            
            # Parse response
            refresh_data = response.json()
            logger.debug(f"Token refresh response received")
            
            if 'accessToken' not in refresh_data or 'expirationTime' not in refresh_data:
                raise TokenRefreshException(
                    f"Invalid token refresh response: missing required fields"
                )
            
            # Parse ISO format date with timezone
            expiration_time = datetime.fromisoformat(
                refresh_data['expirationTime'].replace('Z', '+00:00')
            )
            
            # Update credential in database
            query = """
            UPDATE broker_credentials
            SET access_token = :access_token,
                expires_at = :expires_at,
                is_valid = true,
                refresh_fail_count = 0,
                last_refresh_attempt = :refresh_time,
                last_refresh_error = NULL,
                updated_at = :refresh_time
            WHERE id = :id
            """
            
            refresh_time = datetime.utcnow()
            db.execute(
                query,
                {
                    'access_token': refresh_data['accessToken'],
                    'expires_at': expiration_time,
                    'refresh_time': refresh_time,
                    'id': credential['id']
                }
            )
            
            db.commit()
            
            logger.info(
                f"Token refreshed successfully for credential {credential['id']}, " 
                f"new expiry: {expiration_time}"
            )
            
            # Return updated credential
            return {
                **credential,
                'access_token': refresh_data['accessToken'],
                'expires_at': expiration_time,
                'is_valid': True,
                'refresh_fail_count': 0,
                'last_refresh_attempt': refresh_time,
                'last_refresh_error': None
            }
            
        except httpx.RequestError as e:
            error_msg = f"HTTP request error during token refresh: {str(e)}"
            logger.error(error_msg)
            raise TokenRefreshException(error_msg)
            
        except Exception as e:
            error_msg = f"Error refreshing Tradovate token: {str(e)}"
            logger.error(error_msg)
            raise TokenRefreshException(error_msg)
    
    async def validate_token(self, credential: Dict[str, Any]) -> bool:
        """
        Validate if a Tradovate token is still valid
        
        Args:
            credential: Dictionary containing credential information
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            # Check if token is marked as invalid
            if not credential.get('is_valid', False):
                return False
            
            # Check if token is expired
            expires_at = credential.get('expires_at')
            if not expires_at:
                return False
            
            # If it's a string, convert to datetime
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            
            # Check if expired
            if expires_at <= datetime.utcnow():
                logger.info(f"Token expired for credential {credential.get('id')}")
                return False
            
            # Calculate time until expiry
            seconds_until_expiry = (expires_at - datetime.utcnow()).total_seconds()
            
            # Get refresh threshold in seconds
            refresh_threshold = self.broker_config['REFRESH_THRESHOLD']
            token_lifetime = self.broker_config['TOKEN_LIFETIME']
            refresh_threshold_seconds = refresh_threshold * token_lifetime
            
            # Token is valid if it's not expiring soon
            return seconds_until_expiry > refresh_threshold_seconds
            
        except Exception as e:
            logger.error(f"Error validating token: {str(e)}")
            return False