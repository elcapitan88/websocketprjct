# app/services/tradovate_api.py
import httpx
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import HTTPException
from jose import jwt
from app.models.schemas import AccountInfo, Position, PnL
from app.config import settings

logger = logging.getLogger(__name__)

class TradovateAPIClient:
    def __init__(self):
        self.client_id = settings.TRADOVATE_CLIENT_ID
        self.client_secret = settings.TRADOVATE_CLIENT_SECRET
        self.redirect_uri = settings.TRADOVATE_REDIRECT_URI
        self.auth_url = settings.TRADOVATE_AUTH_URL
        self.token_url = settings.TRADOVATE_TOKEN_URL
        self.api_url = settings.TRADOVATE_API_URL
        self.ws_url = settings.TRADOVATE_WS_URL
        
        # Cache for access tokens
        self.tokens_cache = {}

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange OAuth authorization code for access token"""
        try:
            logger.info(f"Starting token exchange. Code length: {len(code) if code else 0}")
            logger.info(f"Using client_id: {self.client_id}")
            logger.info(f"Using redirect_uri: {self.redirect_uri}")
            logger.info(f"Token URL: {self.token_url}")
            
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri
            }
            
            logger.info(f"Token exchange payload: {payload}")
            
            async with httpx.AsyncClient(timeout=20.0) as client:
                logger.info("Sending token exchange request to Tradovate...")
                response = await client.post(
                    self.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                logger.info(f"Token exchange response status: {response.status_code}")
                response_text = response.text
                logger.info(f"Token exchange response body: {response_text}")
                
                try:
                    token_data = response.json()
                    logger.info(f"Token data keys: {token_data.keys()}")
                    
                    # Check for specific OAuth error responses
                    if "error" in token_data:
                        error_code = token_data.get("error")
                        error_desc = token_data.get("error_description", "")
                        
                        logger.error(f"OAuth error: {error_code} - {error_desc}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"OAuth error: {error_desc}"
                        )
                    
                    # Check what's in the response
                    if "access_token" in token_data:
                        logger.info("Access token found in response")
                        logger.info(f"Access token length: {len(token_data['access_token'])}")
                        
                        # Store in cache with expiration
                        expires_in = token_data.get('expires_in', 86400)  # Default to 24h
                        self.tokens_cache[token_data['access_token']] = {
                            'expires_at': datetime.now() + timedelta(seconds=expires_in),
                            'refresh_token': token_data.get('refresh_token')
                        }
                    else:
                        logger.error("No access_token in token_data")
                        logger.error(f"Available keys: {token_data.keys()}")
                        raise HTTPException(
                            status_code=400,
                            detail="No access token in response from Tradovate"
                        )
                    
                    return token_data
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing token response JSON: {str(e)}")
                    logger.error(f"Raw response: {response_text}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error parsing Tradovate token response: {str(e)}"
                    )
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Token exchange error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error during token exchange: {str(e)}"
            )
    
    async def verify_token(self, token: str) -> bool:
        """Verify if the token is valid by making a test API call to account/list"""
        try:
            # First check if token is in our cache and still valid
            if token in self.tokens_cache:
                cache_entry = self.tokens_cache[token]
                if cache_entry['expires_at'] > datetime.now():
                    logger.info("Token found in cache and still valid")
                    return True
            
            # If not in cache or expired, verify with Tradovate
            logger.info("Verifying token validity using account/list endpoint...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/account/list",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                logger.info(f"Token verification response status: {response.status_code}")
                if response.status_code == 200:
                    logger.info("Token is valid - successfully retrieved account list")
                    
                    # Add to cache if not already there
                    if token not in self.tokens_cache:
                        self.tokens_cache[token] = {
                            'expires_at': datetime.now() + timedelta(hours=23),  # Conservative expiry
                            'refresh_token': None
                        }
                    
                    return True
                else:
                    logger.warning(f"Token verification failed: {response.text}")
                    
                    # Remove from cache if present
                    if token in self.tokens_cache:
                        del self.tokens_cache[token]
                        
                    return False
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return False
        
    async def get_user_data(self, token: str) -> Dict[str, Any]:
        """Get current user data"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/me",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get user data: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to get user data"
                    )
                
                return response.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting user data: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting user data: {str(e)}"
            )

    async def get_ws_connection_details(self, token: str) -> Dict[str, Any]:
        """Get WebSocket connection details for frontend"""
        if not await self.verify_token(token):
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )
            
        return {
            "ws_url": self.ws_url,
            "token": token
        }
    
    # Add this method to your TradovateAPIClient class in tradovate_api.py

    async def get_account_info(self, token: str) -> AccountInfo:
        """Get user account information"""
        try:
            async with httpx.AsyncClient() as client:
                # Get account info directly without calling /me endpoint
                logger.info("Getting account information...")
                account_response = await client.get(
                    f"{self.api_url}/account/list",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if account_response.status_code != 200:
                    logger.error(f"Failed to get account info: {account_response.text}")
                    raise HTTPException(
                        status_code=account_response.status_code,
                        detail="Failed to get account information"
                    )
                
                accounts = account_response.json()
                logger.info(f"Retrieved {len(accounts)} accounts")
                
                if not accounts:
                    raise HTTPException(
                        status_code=404,
                        detail="No accounts found for this user"
                    )
                
                # Use the first active account
                active_accounts = [acc for acc in accounts if acc.get("active", False)]
                
                if not active_accounts:
                    # If no active account, just take the first one
                    account = accounts[0]
                else:
                    account = active_accounts[0]
                
                # Use accountId as userId if userId isn't available directly
                # Many platforms use the account's userId or ownerId field
                user_id = account.get("userId", account.get("ownerId", account["id"]))
                
                # Format data according to our schema
                return AccountInfo(
                    id=account["id"],
                    name=account["name"],
                    userId=user_id,  # Use the extracted or default user ID
                    accountType=account.get("accountType", "Unknown"),
                    active=account.get("active", False),
                    tradingEnabled=account.get("tradingEnabled", False),
                    marginEnabled=account.get("marginEnabled", False),
                    cashBalance=account.get("cashBalance", 0.0),
                    status=account.get("active", False)
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting account info: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting account information: {str(e)}"
            )

    def create_jwt_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT token for internal authentication"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

# Create a global instance
tradovate_client = TradovateAPIClient()