import asyncio
import json
import logging
import websockets
from typing import Dict, List, Set, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
import random  # For demo data simulation

from app.models.schemas import AccountInfo, Position, PnL, WebSocketMessage
from app.services.tradovate_api import tradovate_client

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.tradovate_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.token_to_account_id: Dict[str, int] = {}
        
    async def connect(self, websocket: WebSocket, token: str):
        """Connect a client WebSocket"""
        try:
            # Accept the WebSocket connection
            await websocket.accept()
            
            # Verify the token
            is_valid = await tradovate_client.verify_token(token)
            if not is_valid:
                await websocket.close(code=1008, reason="Invalid token")
                return False
            
            # Get account info
            account_info = await tradovate_client.get_account_info(token)
            account_id = account_info.id
            
            # Store the connection with token as key
            self.active_connections[token] = websocket
            self.token_to_account_id[token] = account_id
            
            # Send initial account info
            await self.send_account_info(token, account_info)
            
            # Get and send initial positions
            positions = await tradovate_client.get_positions(token, account_id)
            await self.send_positions(token, positions)
            
            # Get and send initial PnL
            pnl = await tradovate_client.get_pnl(token, account_id)
            await self.send_pnl(token, pnl)
            
            # In a real implementation, we would connect to Tradovate WebSocket here
            # For the demo, we'll use a simulation
            asyncio.create_task(self.simulate_tradovate_updates(token, account_id))
            
            return True
            
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {str(e)}")
            try:
                await websocket.close(code=1011, reason="Server error")
            except:
                pass
            return False

    async def disconnect(self, token: str):
        """Disconnect a client WebSocket"""
        if token in self.active_connections:
            # Close the connection to Tradovate if it exists
            if token in self.tradovate_connections:
                try:
                    await self.tradovate_connections[token].close()
                    del self.tradovate_connections[token]
                except:
                    pass
            
            # Remove the connection
            del self.active_connections[token]
            
            # Remove the account ID mapping
            if token in self.token_to_account_id:
                del self.token_to_account_id[token]

    async def send_message(self, token: str, message: Any):
        """Send a message to a specific client"""
        if token in self.active_connections:
            try:
                # If message is not a string, convert to JSON
                if not isinstance(message, str):
                    message = json.dumps(message)
                    
                await self.active_connections[token].send_text(message)
            except Exception as e:
                logger.error(f"Error sending message: {str(e)}")
                await self.disconnect(token)

    async def send_account_info(self, token: str, account_info: AccountInfo):
        """Send account info to a client"""
        message = WebSocketMessage(
            type="account_info",
            payload=account_info
        )
        await self.send_message(token, message.dict())

    async def send_positions(self, token: str, positions: List[Position]):
        """Send positions to a client"""
        message = WebSocketMessage(
            type="positions",
            payload=positions
        )
        await self.send_message(token, message.dict())

    async def send_pnl(self, token: str, pnl: PnL):
        """Send PnL to a client"""
        message = WebSocketMessage(
            type="pnl",
            payload=pnl
        )
        await self.send_message(token, message.dict())

    async def simulate_tradovate_updates(self, token: str, account_id: int):
        """Simulate real-time updates from Tradovate WebSocket"""
        try:
            # In a real implementation, we would connect to Tradovate's WebSocket API
            # and forward events to our client. For demo purposes, we'll simulate data.
            
            # Generate some initial positions
            symbols = ["ES", "NQ", "YM", "RTY", "CL", "GC"]
            positions = []
            
            # Create 1-3 random positions
            num_positions = random.randint(1, 3)
            for i in range(num_positions):
                symbol = random.choice(symbols)
                net_pos = random.choice([-5, -3, -2, -1, 1, 2, 3, 5])
                entry_price = round(random.uniform(1000, 5000), 2)
                market_price = entry_price  # Start at breakeven
                
                positions.append(Position(
                    id=i + 1000,
                    accountId=account_id,
                    contractId=i + 2000,
                    netPos=net_pos,
                    netPrice=entry_price,
                    timestamp=datetime.now().isoformat(),
                    symbol=symbol,
                    entryPrice=entry_price,
                    marketPrice=market_price,
                    pnl=0.0  # Start at breakeven
                ))
            
            # Send initial positions
            await self.send_positions(token, positions)
            
            # Calculate and send initial PnL
            pnl = PnL(
                netPnl=0.0,
                realizedPnl=0.0,
                unrealizedPnl=0.0,
                accountId=account_id
            )
            await self.send_pnl(token, pnl)
            
            # Continuous updates
            while token in self.active_connections:
                # Wait a random interval (1-5 seconds)
                await asyncio.sleep(random.uniform(1, 5))
                
                # Update market prices and PnL
                total_pnl = 0.0
                for position in positions:
                    # Random price change (-0.5% to +0.5%)
                    price_change_pct = random.uniform(-0.005, 0.005)
                    new_market_price = position.marketPrice * (1 + price_change_pct)
                    position.marketPrice = round(new_market_price, 2)
                    
                    # Calculate new PnL
                    position.pnl = round((position.marketPrice - position.entryPrice) * position.netPos, 2)
                    total_pnl += position.pnl
                
                # Send updated positions
                await self.send_positions(token, positions)
                
                # Update PnL
                # In a real system, this would come from Tradovate
                # For demo, we'll calculate from our simulated positions
                unrealized_pnl = total_pnl
                realized_pnl = pnl.realizedPnl  # Unchanged for demo
                
                new_pnl = PnL(
                    netPnl=round(realized_pnl + unrealized_pnl, 2),
                    realizedPnl=realized_pnl,
                    unrealizedPnl=round(unrealized_pnl, 2),
                    accountId=account_id
                )
                
                # Only send if PnL changed
                if new_pnl.netPnl != pnl.netPnl or new_pnl.unrealizedPnl != pnl.unrealizedPnl:
                    pnl = new_pnl
                    await self.send_pnl(token, pnl)
                
                # Occasionally (10% chance), modify a position
                if random.random() < 0.1:
                    if positions and len(positions) > 0:
                        # Pick a random position
                        pos_idx = random.randint(0, len(positions) - 1)
                        position = positions[pos_idx]
                        
                        # Either modify qty or close position
                        if random.random() < 0.7:
                            # Modify quantity
                            qty_change = random.choice([-2, -1, 1, 2])
                            new_qty = position.netPos + qty_change
                            
                            if new_qty != 0:
                                position.netPos = new_qty
                                # Recalculate PnL
                                position.pnl = round((position.marketPrice - position.entryPrice) * position.netPos, 2)
                            else:
                                # If new qty is 0, close the position
                                closed_pnl = position.pnl
                                positions.pop(pos_idx)
                                
                                # Add to realized PnL
                                pnl.realizedPnl = round(pnl.realizedPnl + closed_pnl, 2)
                                pnl.netPnl = round(pnl.realizedPnl + pnl.unrealizedPnl, 2)
                        else:
                            # Close position
                            closed_pnl = position.pnl
                            positions.pop(pos_idx)
                            
                            # Add to realized PnL
                            pnl.realizedPnl = round(pnl.realizedPnl + closed_pnl, 2)
                            pnl.netPnl = round(pnl.realizedPnl + pnl.unrealizedPnl, 2)
                        
                        # Send updated positions and PnL
                        await self.send_positions(token, positions)
                        await self.send_pnl(token, pnl)
                
                # Occasionally (5% chance), add a new position
                if random.random() < 0.05:
                    symbol = random.choice(symbols)
                    net_pos = random.choice([-5, -3, -2, -1, 1, 2, 3, 5])
                    entry_price = round(random.uniform(1000, 5000), 2)
                    market_price = entry_price  # Start at breakeven
                    
                    new_position = Position(
                        id=len(positions) + 1000,
                        accountId=account_id,
                        contractId=len(positions) + 2000,
                        netPos=net_pos,
                        netPrice=entry_price,
                        timestamp=datetime.now().isoformat(),
                        symbol=symbol,
                        entryPrice=entry_price,
                        marketPrice=market_price,
                        pnl=0.0  # Start at breakeven
                    )
                    
                    positions.append(new_position)
                    await self.send_positions(token, positions)
        
        except Exception as e:
            logger.error(f"Error in Tradovate simulation: {str(e)}")
        finally:
            # If we exit the loop, ensure we disconnect
            if token in self.active_connections:
                try:
                    await self.disconnect(token)
                except:
                    pass

# Create a global instance
websocket_manager = WebSocketManager()