from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
import logging

from app.config import settings
from app.models.schemas import TokenRequest, TokenResponse, ErrorResponse
from app.services.tradovate_api import tradovate_client

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# OAuth2 scheme for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Token validation dependency
async def get_current_token(token: str = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Verify JWT token
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        tradovate_token = payload.get("tradovate_token")
        if tradovate_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify that the Tradovate token is still valid
        is_valid = await tradovate_client.verify_token(tradovate_token)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired or invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return tradovate_token
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/oauth/token", response_model=TokenResponse)
async def exchange_code_for_token(token_request: TokenRequest):
    """Exchange OAuth authorization code for access token"""
    try:
        # Exchange code for Tradovate token
        tradovate_token_data = await tradovate_client.exchange_code_for_token(token_request.code)
        
        # Get access token from response
        tradovate_access_token = tradovate_token_data.get("access_token")
        if not tradovate_access_token:
            logger.error("No access token in Tradovate response")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get access token from Tradovate",
            )
        
        # Create our own JWT token that contains the Tradovate token
        expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = tradovate_client.create_jwt_token(
            data={"tradovate_token": tradovate_access_token},
            expires_delta=expires
        )
        
        # Return token response
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=tradovate_token_data.get("refresh_token")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing token: {str(e)}",
        )

@router.get("/verify-token")
async def verify_token(token: str = Depends(get_current_token)):
    """Verify if token is valid"""
    # If we got here, token is valid
    return {"status": "valid"}

@router.get("/account-info")
async def get_account_info(token: str = Depends(get_current_token)):
    """Get account information for the authenticated user"""
    try:
        account_info = await tradovate_client.get_account_info(token)
        return account_info
    except Exception as e:
        logger.error(f"Error getting account info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting account info: {str(e)}",
        )

@router.post("/logout")
async def logout(token: str = Depends(get_current_token)):
    """Logout user by invalidating token"""
    # In a production system, we would:
    # 1. Add token to a blocklist or
    # 2. Revoke the token on Tradovate's side if they support it
    # For this demo, we'll just return success
    return {"status": "success"}