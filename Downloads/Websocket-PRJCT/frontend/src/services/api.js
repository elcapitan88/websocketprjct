// src/services/api.js

// Base URL for our backend API
const API_BASE_URL = 'http://localhost:8000/api';

// Helper function to handle API responses
const handleResponse = async (response) => {
  if (!response.ok) {
    // Get error message from the response body
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || `API error: ${response.status}`);
  }
  return response.json();
};

// API service object
const apiService = {
  // Exchange OAuth code for access token
  exchangeCodeForToken: async (code) => {
    try {
      const response = await fetch(`${API_BASE_URL}/oauth/token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code }),
      });
      
      return handleResponse(response);
    } catch (error) {
      console.error('Error exchanging code for token:', error);
      throw error;
    }
  },
  
  // Verify token is still valid
  verifyToken: async (token) => {
    try {
      const response = await fetch(`${API_BASE_URL}/verify-token`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      
      return response.ok;
    } catch (error) {
      console.error('Error verifying token:', error);
      return false;
    }
  },
  
  // Get account information
  getAccountInfo: async (token) => {
    try {
      const response = await fetch(`${API_BASE_URL}/account-info`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      
      return handleResponse(response);
    } catch (error) {
      console.error('Error fetching account info:', error);
      throw error;
    }
  },
  
  // Logout (revoke token)
  logout: async (token) => {
    try {
      const response = await fetch(`${API_BASE_URL}/logout`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      
      return response.ok;
    } catch (error) {
      console.error('Error during logout:', error);
      return false;
    }
  }
};

export default apiService;