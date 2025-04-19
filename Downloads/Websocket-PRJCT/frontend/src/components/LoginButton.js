import React, { useState } from 'react';
import apiService from '../services/api';

const LoginButton = ({ onLoginSuccess }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Tradovate OAuth configuration
  const clientId = '5922'; // Ensure this matches your Tradovate client ID
  const redirectUri = 'http://localhost:3000/callback'; // Must match your Tradovate developer settings

  // Function to initiate OAuth flow
  const handleLogin = () => {
    try {
      setIsLoading(true);
      setError(null);
      
      // Generate and store a random state parameter for security
      const state = Math.random().toString(36).substring(2, 15);
      localStorage.setItem('oauth_state', state);
      
      // Build the OAuth authorization URL
      const authUrl = `https://trader.tradovate.com/oauth?` +
        `response_type=code&` +
        `client_id=${clientId}&` +
        `redirect_uri=${encodeURIComponent(redirectUri)}&` +
        `state=${state}`;
      
      // Navigate to Tradovate's authorization page in the current window
      window.location.href = authUrl;
    } catch (err) {
      setError('Failed to initiate authentication process');
      setIsLoading(false);
      console.error('Login error:', err);
    }
  };

  return (
    <div className="login-container">
      {error && <div className="error-message">{error}</div>}
      <button 
        className="login-button" 
        onClick={handleLogin} 
        disabled={isLoading}
      >
        {isLoading ? 'Connecting...' : 'Connect to Tradovate'}
      </button>
      <p className="login-help">
        You will be redirected to Tradovate to authenticate your account.
      </p>
    </div>
  );
};

export default LoginButton;