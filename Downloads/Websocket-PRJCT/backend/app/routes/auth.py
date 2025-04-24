from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
import logging
from typing import Optional
import time

from app.config import settings
from app.models.schemas import TokenRequest, TokenResponse, ErrorResponse
from app.services.tradovate_api import tradovate_client

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# OAuth2 scheme for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Simple in-memory cache for processed authorization codes
# Format: {"code": (timestamp, result)}
processed_codes = {}
CODE_EXPIRY_SECONDS = 300  # 5 minutes expiry for processed codes

# Clean up expired codes from cache
def clean_expired_codes():
    current_time = time.time()
    expired_codes = [code for code, (timestamp, _) in processed_codes.items() 
                    if current_time - timestamp > CODE_EXPIRY_SECONDS]
    
    for code in expired_codes:
        del processed_codes[code]
    
    if expired_codes:
        logger.info(f"Cleaned up {len(expired_codes)} expired authorization codes from cache")

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
async def exchange_code_for_token(
    request: Request,
    token_request: TokenRequest, 
    x_request_id: Optional[str] = Header(None)
):
    """Exchange OAuth authorization code for access token with deduplication"""
    
    # Clean expired codes periodically
    clean_expired_codes()
    
    try:
        code = token_request.code
        request_id = x_request_id or request.client.host
        
        logger.info(f"Received token exchange request. Code length: {len(code) if code else 0}, Request ID: {request_id}")
        
        # Check if this code has already been processed
        if code in processed_codes:
            timestamp, result = processed_codes[code]
            logger.warning(f"Authorization code already processed at {datetime.fromtimestamp(timestamp)}")
            
            if isinstance(result, Exception):
                # If previous attempt resulted in error, return the same error
                logger.error(f"Returning cached error for previously processed code: {result}")
                if isinstance(result, HTTPException):
                    raise result
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Authorization code already used: {str(result)}"
                    )
            else:
                # If previous attempt was successful, return the cached result
                logger.info(f"Returning cached result for previously processed code")
                return result
        
        # Mark code as being processed
        processed_codes[code] = (time.time(), None)
        
        logger.info("Calling tradovate_client.exchange_code_for_token...")
        
        # Exchange code for Tradovate token
        try:
            tradovate_token_data = await tradovate_client.exchange_code_for_token(code)
            
            logger.info(f"Token data received: {tradovate_token_data.keys() if tradovate_token_data else None}")
            
            # Get access token from response
            tradovate_access_token = tradovate_token_data.get("access_token")
            if not tradovate_access_token:
                logger.error("No access token in Tradovate response")
                logger.error(f"Complete response: {tradovate_token_data}")
                
                # Check for specific error messages
                if tradovate_token_data.get("error") == "invalid_grant" and "used already" in tradovate_token_data.get("error_description", ""):
                    error = HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Authorization code has already been used"
                    )
                else:
                    error = HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to get access token from Tradovate"
                    )
                
                # Cache the error
                processed_codes[code] = (time.time(), error)
                raise error
            
            logger.info(f"Access token received, length: {len(tradovate_access_token)}")
            
            # Create our own JWT token that contains the Tradovate token
            expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = tradovate_client.create_jwt_token(
                data={"tradovate_token": tradovate_access_token},
                expires_delta=expires
            )
            
            logger.info("JWT token created successfully")
            
            # Create token response
            token_response = TokenResponse(
                access_token=access_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                refresh_token=tradovate_token_data.get("refresh_token")
            )
            
            # Cache the successful result
            processed_codes[code] = (time.time(), token_response)
            
            # Return token response
            return token_response
            
        except HTTPException as e:
            # Cache the HTTP exception
            processed_codes[code] = (time.time(), e)
            raise
        except Exception as e:
            logger.error(f"Error in token exchange: {str(e)}", exc_info=True)
            error = HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing token: {str(e)}",
            )
            # Cache the error
            processed_codes[code] = (time.time(), error)
            raise error
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in token exchange endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )
    
    
@router.get("/websocket-details")
async def get_websocket_details(token: str = Depends(get_current_token)):
    """Get WebSocket connection details for connecting to Tradovate"""
    try:
        # Get WebSocket connection details from Tradovate client
        ws_details = await tradovate_client.get_ws_connection_details(token)
        
        return {
            "ws_url": ws_details["ws_url"],
            "token": token,  # Pass the Tradovate token directly for WebSocket auth
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting WebSocket details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting WebSocket connection details: {str(e)}",
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