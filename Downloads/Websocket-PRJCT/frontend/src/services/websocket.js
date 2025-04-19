// src/services/websocket.js

class WebSocketService {
    constructor() {
      this.ws = null;
      this.callbacks = {
        accountInfo: null,
        positions: null,
        pnl: null,
        onOpen: null,
        onClose: null,
        onError: null
      };
    }
  
    connect(token) {
      if (this.ws) {
        this.disconnect();
      }
  
      this.ws = new WebSocket(`ws://localhost:8000/ws?token=${token}`);
  
      this.ws.onopen = () => {
        console.log('WebSocket connection established');
        if (this.callbacks.onOpen) {
          this.callbacks.onOpen();
        }
      };
  
      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'account_info' && this.callbacks.accountInfo) {
            this.callbacks.accountInfo(data.payload);
          } else if (data.type === 'positions' && this.callbacks.positions) {
            this.callbacks.positions(data.payload);
          } else if (data.type === 'pnl' && this.callbacks.pnl) {
            this.callbacks.pnl(data.payload);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };
  
      this.ws.onclose = () => {
        console.log('WebSocket connection closed');
        if (this.callbacks.onClose) {
          this.callbacks.onClose();
        }
      };
  
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        if (this.callbacks.onError) {
          this.callbacks.onError(error);
        }
      };
    }
  
    disconnect() {
      if (this.ws) {
        this.ws.close();
        this.ws = null;
      }
    }
  
    onAccountInfo(callback) {
      this.callbacks.accountInfo = callback;
    }
  
    onPositions(callback) {
      this.callbacks.positions = callback;
    }
  
    onPnL(callback) {
      this.callbacks.pnl = callback;
    }
  
    onOpen(callback) {
      this.callbacks.onOpen = callback;
    }
  
    onClose(callback) {
      this.callbacks.onClose = callback;
    }
  
    onError(callback) {
      this.callbacks.onError = callback;
    }
  
    isConnected() {
      return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
  }
  
  // Create a singleton instance
  const websocketService = new WebSocketService();
  
  export default websocketService;