from pydantic import BaseModel
from typing import Optional, List, Union, Dict, Any

# OAuth related models
class TokenRequest(BaseModel):
    code: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None

# Tradovate API models
class AccountInfo(BaseModel):
    id: int
    name: str
    userId: int
    accountType: str
    active: bool
    tradingEnabled: bool
    marginEnabled: bool
    cashBalance: float
    status: bool = True  # Simplified status for frontend

class Position(BaseModel):
    id: int
    accountId: int
    contractId: int
    netPos: float
    netPrice: Optional[float] = None
    timestamp: str
    symbol: str  # Added for frontend display
    entryPrice: Optional[float] = None  # Added for frontend display
    marketPrice: Optional[float] = None  # Added for frontend display
    pnl: Optional[float] = None  # Added for frontend display

class PnL(BaseModel):
    netPnl: float
    realizedPnl: float
    unrealizedPnl: float
    accountId: int

# WebSocket message models
class WebSocketMessage(BaseModel):
    type: str
    payload: Union[AccountInfo, List[Position], PnL, Dict[str, Any]]

# Error model
class ErrorResponse(BaseModel):
    message: str
    detail: Optional[str] = None