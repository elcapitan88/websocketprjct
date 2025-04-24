# app/services/websocket.py

import asyncio
import json
import logging
import websockets
from typing import Dict, List, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

from app.models.schemas import AccountInfo, Position, PnL, WebSocketMessage
from app.services.tradovate_api import tradovate_client

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.tradovate_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.token_to_account_id: Dict[str, int] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        
    async def connect(self, websocket: WebSocket, token: str) -> bool:
        """Connect a client WebSocket and establish connection to Tradovate"""
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
            
            # Connect to Tradovate WebSocket
            await self.connect_to_tradovate(token, account_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {str(e)}")
            try:
                await websocket.close(code=1011, reason="Server error")
            except:
                pass
            return False

    async def connect_to_tradovate(self, token: str, account_id: int):
        """Establish connection to Tradovate WebSocket"""
        if token in self.tradovate_connections:
            # Already connected
            return
            
        try:
            # Get WebSocket URL from settings
            ws_url = tradovate_client.ws_url
            logger.info(f"Connecting to Tradovate WebSocket at {ws_url}")
            
            # Connect to Tradovate WebSocket
            tradovate_ws = await websockets.connect(ws_url)
            self.tradovate_connections[token] = tradovate_ws
            
            # Start heartbeat task
            self.heartbeat_tasks[token] = asyncio.create_task(
                self.handle_tradovate_heartbeat(token, tradovate_ws)
            )
            
            # Start message handler task
            asyncio.create_task(
                self.handle_tradovate_messages(token, tradovate_ws, account_id)
            )
            
        except Exception as e:
            logger.error(f"Error connecting to Tradovate WebSocket: {str(e)}")
            if token in self.active_connections:
                try:
                    await self.active_connections[token].close(
                        code=1011, 
                        reason="Error connecting to Tradovate"
                    )
                except:
                    pass
                    
            await self.disconnect(token)

    async def handle_tradovate_heartbeat(self, token: str, ws: websockets.WebSocketClientProtocol):
        """Handle heartbeat for Tradovate WebSocket connection"""
        try:
            last_heartbeat = datetime.now()
            
            while token in self.tradovate_connections:
                # Send heartbeat every 2.5 seconds
                current_time = datetime.now()
                if (current_time - last_heartbeat).total_seconds() >= 2.5:
                    logger.debug("Sending heartbeat to Tradovate")
                    await ws.send("[]")  # Empty array is the heartbeat
                    last_heartbeat = current_time
                    
                # Check for any messages without blocking too long
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Error in Tradovate heartbeat handler: {str(e)}")
            await self.disconnect(token)

    async def handle_tradovate_messages(self, token: str, ws: websockets.WebSocketClientProtocol, account_id: int):
        """Handle messages from Tradovate WebSocket"""
        try:
            # Wait for the initial open frame ('o')
            msg = await ws.recv()
            logger.info(f"Tradovate WebSocket initial message: {msg}")
            
            if msg.startswith('o'):
                # Send authorization request
                auth_request = f"authorize\n1\n\n{token}"
                logger.info("Sending authorization request to Tradovate")
                await ws.send(auth_request)
                
                # Wait for authorization response
                while token in self.tradovate_connections:
                    msg = await ws.recv()
                    logger.debug(f"Received from Tradovate: {msg}")
                    
                    # Skip heartbeat messages
                    if msg.startswith('h'):
                        logger.debug("Received heartbeat from Tradovate")
                        continue
                        
                    # Process data messages
                    if msg.startswith('a'):
                        data_str = msg[1:]  # Remove the 'a' prefix
                        data = json.loads(data_str)
                        
                        # Process each response in the array
                        for response in data:
                            logger.info(f"Processing Tradovate response: {response}")
                            
                            # Check if this is the auth response
                            if response.get('s') == 200 and response.get('i') == 1:
                                logger.info("Successfully authorized with Tradovate, subscribing to data")
                                
                                # Subscribe to user account updates
                                subscribe_request = f"user/syncrequest\n2\n\n{{\"users\": [{account_id}]}}"
                                await ws.send(subscribe_request)
                                
                            # Process entity data for ongoing updates
                            elif 'e' in response and response['e'] == 'props':
                                if 'd' in response:
                                    entity_data = response['d']
                                    if 'entity' in entity_data and 'entityType' in entity_data:
                                        await self.process_entity_update(token, entity_data)
                                        
                            # Process initial sync data
                            elif 'd' in response and 'users' in response['d']:
                                await self.process_initial_sync(token, response['d'])
                                
            else:
                logger.error(f"Unexpected initial message from Tradovate: {msg}")
                await self.disconnect(token)
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"Tradovate WebSocket connection closed: {e}")
            await self.disconnect(token)
        except Exception as e:
            logger.error(f"Error in Tradovate message handler: {str(e)}")
            await self.disconnect(token)

    async def process_account_update(self, token: str, data: Dict[str, Any]):
        """Process account updates from Tradovate"""
        try:
            account_info = AccountInfo(
                id=data.get('id'),
                name=data.get('name', 'Unknown'),
                userId=data.get('userId', 0),
                accountType=data.get('accountType', 'Unknown'),
                active=data.get('active', False),
                tradingEnabled=data.get('tradingEnabled', False),
                marginEnabled=data.get('marginEnabled', False),
                cashBalance=data.get('cashBalance', 0.0),
                status=data.get('active', False)
            )
            
            await self.send_account_info(token, account_info)
            
        except Exception as e:
            logger.error(f"Error processing account update: {str(e)}")

    async def process_position_update(self, token: str, data: Dict[str, Any]):
        """Process position updates from Tradovate"""
        try:
            # We need to fetch contract info to get symbol
            # For now, use a placeholder
            symbol = f"Contract-{data.get('contractId', 'Unknown')}"
            
            position = Position(
                id=data.get('id', 0),
                accountId=data.get('accountId', 0),
                contractId=data.get('contractId', 0),
                netPos=data.get('netPos', 0),
                netPrice=data.get('netPrice', 0),
                timestamp=data.get('timestamp', datetime.now().isoformat()),
                symbol=symbol,
                entryPrice=data.get('avgPrice', 0),
                marketPrice=data.get('lastPrice', data.get('avgPrice', 0)),
                pnl=data.get('pnl', 0)
            )
            
            # Get all positions for this account
            positions = [position]  # In a real impl, we'd maintain a list of all positions
            
            await self.send_positions(token, positions)
            
        except Exception as e:
            logger.error(f"Error processing position update: {str(e)}")

    async def process_cash_balance_update(self, token: str, data: Dict[str, Any], account_id: int):
        """Process cash balance updates from Tradovate"""
        try:
            # In a real implementation, we'd calculate PnL from positions
            # For now, use simplified values
            pnl = PnL(
                netPnl=data.get('cashBalance', 0),
                realizedPnl=0,  # Would need real data from Tradovate
                unrealizedPnl=0,  # Would need real data from Tradovate
                accountId=account_id
            )
            
            await self.send_pnl(token, pnl)
            
        except Exception as e:
            logger.error(f"Error processing cash balance update: {str(e)}")

    async def disconnect(self, token: str):
        """Disconnect a client and clean up resources"""
        # Close Tradovate connection
        if token in self.tradovate_connections:
            try:
                await self.tradovate_connections[token].close()
            except:
                pass
            del self.tradovate_connections[token]
            
        # Cancel heartbeat task
        if token in self.heartbeat_tasks:
            self.heartbeat_tasks[token].cancel()
            del self.heartbeat_tasks[token]
            
        # Remove client connection
        if token in self.active_connections:
            try:
                await self.active_connections[token].close()
            except:
                pass
            del self.active_connections[token]
            
        # Clean up account mapping
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

# Create a global instance
websocket_manager = WebSocketManager()