from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, status
from jose import JWTError, jwt
import logging

from app.config import settings
from app.services.websocket import websocket_manager

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

async def get_token_from_query(token: str = Query(...)):
    """Validate the JWT token from WebSocket query parameters"""
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
            
        return tradovate_token
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """WebSocket endpoint for real-time trading data"""
    try:
        # Validate the token
        tradovate_token = None
        try:
            tradovate_token = await get_token_from_query(token)
        except HTTPException as e:
            await websocket.accept()
            await websocket.close(code=1008, reason=str(e.detail))
            return
        
        # Connect to the WebSocket manager
        connected = await websocket_manager.connect(websocket, tradovate_token)
        if not connected:
            return
        
        try:
            # Keep the connection alive until disconnection
            while True:
                # Wait for messages from the client (if needed)
                # For now, we just keep the connection open
                data = await websocket.receive_text()
                
                # Process client messages if needed
                # In this simple example, we're just receiving data from Tradovate
                # and forwarding it to the client
                
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            await websocket_manager.disconnect(tradovate_token)
            
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}")
        try:
            # Try to close the WebSocket if there's an error
            await websocket.close(code=1011, reason="Server error")
        except:
            pass