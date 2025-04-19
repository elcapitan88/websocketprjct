import httpx
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from fastapi import HTTPException
from jose import jwt

from app.config import settings
from app.models.schemas import AccountInfo, Position, PnL

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
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Token exchange failed: {response.text}")
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to exchange code for token"
                    )
                
                token_data = response.json()
                
                # Store token in cache with user ID as key
                # We'll extract user ID when we get account info
                
                return token_data
                
        except Exception as e:
            logger.error(f"Token exchange error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error during token exchange: {str(e)}"
            )

    async def verify_token(self, token: str) -> bool:
        """Verify if the token is valid by making a test API call"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/me",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return False

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh the access token using a refresh token"""
        try:
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Token refresh failed: {response.text}")
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to refresh token"
                    )
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error during token refresh: {str(e)}"
            )

    async def get_account_info(self, token: str) -> AccountInfo:
        """Get user account information"""
        try:
            async with httpx.AsyncClient() as client:
                # First get user info
                user_response = await client.get(
                    f"{self.api_url}/me",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if user_response.status_code != 200:
                    logger.error(f"Failed to get user info: {user_response.text}")
                    raise HTTPException(
                        status_code=user_response.status_code,
                        detail="Failed to get user information"
                    )
                
                user_data = user_response.json()
                user_id = user_data["userId"]
                
                # Then get account info
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
                
                # Format data according to our schema
                return AccountInfo(
                    id=account["id"],
                    name=account["name"],
                    userId=user_id,
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

    async def get_positions(self, token: str, account_id: int) -> List[Position]:
        """Get positions for an account"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/position/list?accountId={account_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get positions: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to get positions"
                    )
                
                positions_data = response.json()
                
                # We need to enrich positions with contract info and current prices
                positions = []
                for pos in positions_data:
                    # Skip positions with zero quantity
                    if pos.get("netPos", 0) == 0:
                        continue
                    
                    # Get contract info for symbol
                    contract_id = pos.get("contractId")
                    contract_response = await client.get(
                        f"{self.api_url}/contract/item?id={contract_id}",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    
                    if contract_response.status_code != 200:
                        logger.warning(f"Failed to get contract info: {contract_response.text}")
                        symbol = f"Unknown-{contract_id}"
                    else:
                        contract = contract_response.json()
                        symbol = contract.get("name", f"Unknown-{contract_id}")
                    
                    # Get current price (placeholder - would need market data subscription)
                    # In a real implementation, this would come from WebSocket market data
                    market_price = pos.get("netPrice", 0)  # Placeholder
                    
                    # Calculate PnL (placeholder)
                    # In a real implementation, this would be more accurate
                    entry_price = pos.get("avgPrice", 0)
                    net_pos = pos.get("netPos", 0)
                    pnl = (market_price - entry_price) * net_pos  # Simplified
                    
                    positions.append(Position(
                        id=pos["id"],
                        accountId=pos["accountId"],
                        contractId=pos["contractId"],
                        netPos=pos["netPos"],
                        netPrice=pos.get("netPrice"),
                        timestamp=pos.get("timestamp", datetime.now().isoformat()),
                        symbol=symbol,
                        entryPrice=entry_price,
                        marketPrice=market_price,
                        pnl=pnl
                    ))
                
                return positions
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting positions: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting positions: {str(e)}"
            )

    async def get_pnl(self, token: str, account_id: int) -> PnL:
        """Get PnL for an account"""
        try:
            async with httpx.AsyncClient() as client:
                # In a real implementation, we would get this from a specific endpoint
                # For now, we'll calculate it from positions (simplified)
                positions = await self.get_positions(token, account_id)
                
                realized_pnl = 0.0  # Would come from closed positions
                unrealized_pnl = sum(pos.pnl or 0.0 for pos in positions)
                net_pnl = realized_pnl + unrealized_pnl
                
                return PnL(
                    netPnl=net_pnl,
                    realizedPnl=realized_pnl,
                    unrealizedPnl=unrealized_pnl,
                    accountId=account_id
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting PnL: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting PnL: {str(e)}"
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