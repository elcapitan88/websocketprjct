import React, { useState, useEffect } from 'react';
import LoginButton from './components/LoginButton';
import AccountInfo from './components/AccountInfo';
import PositionsList from './components/PositionsList';
import PnLDisplay from './components/PnLDisplay';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [accountInfo, setAccountInfo] = useState(null);
  const [positions, setPositions] = useState([]);
  const [pnl, setPnl] = useState(null);
  const [websocket, setWebsocket] = useState(null);

  // Check if user is already authenticated on component mount
  useEffect(() => {
    const token = localStorage.getItem('tradovateToken');
    if (token) {
      // Verify token validity with backend
      fetch('http://localhost:8000/api/verify-token', {
        headers: {
          Authorization: `Bearer ${token}`
        }
      })
      .then(response => {
        if (response.ok) {
          setIsAuthenticated(true);
          // Initialize websocket connection after authentication
          initWebsocket(token);
        } else {
          localStorage.removeItem('tradovateToken');
        }
      })
      .catch(error => {
        console.error('Error verifying token:', error);
        localStorage.removeItem('tradovateToken');
      });
    }
  }, []);

  // Initialize WebSocket connection
  const initWebsocket = (token) => {
    const ws = new WebSocket(`ws://localhost:8000/ws?token=${token}`);
    
    ws.onopen = () => {
      console.log('WebSocket connection established');
      setWebsocket(ws);
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'account_info') {
        setAccountInfo(data.payload);
      } else if (data.type === 'positions') {
        setPositions(data.payload);
      } else if (data.type === 'pnl') {
        setPnl(data.payload);
      }
    };
    
    ws.onclose = () => {
      console.log('WebSocket connection closed');
      setWebsocket(null);
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    // Clean up the websocket on component unmount
    return () => {
      if (ws) {
        ws.close();
      }
    };
  };

  // Handle successful OAuth login
  const handleLoginSuccess = (token) => {
    localStorage.setItem('tradovateToken', token);
    setIsAuthenticated(true);
    initWebsocket(token);
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Tradovate Position Monitor</h1>
      </header>
      
      <main>
        {!isAuthenticated ? (
          <div className="card">
            <h2>Connect to Tradovate</h2>
            <LoginButton onLoginSuccess={handleLoginSuccess} />
          </div>
        ) : (
          <>
            {accountInfo && (
              <AccountInfo account={accountInfo} />
            )}
            
            <div className="dashboard">
              <PnLDisplay pnl={pnl} />
              <PositionsList positions={positions} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default App;