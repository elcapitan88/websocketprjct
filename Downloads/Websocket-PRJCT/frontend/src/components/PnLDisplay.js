import React from 'react';

const PnLDisplay = ({ pnl }) => {
  // If PnL data is not provided
  if (!pnl) {
    return (
      <div className="card pnl-display">
        <h2>Profit & Loss</h2>
        <p>PnL data not available.</p>
      </div>
    );
  }

  // Determine if overall PnL is positive or negative for styling
  const isProfitable = pnl.netPnl > 0;
  
  return (
    <div className="card pnl-display">
      <h2>Profit & Loss</h2>
      <div className="pnl-summary">
        <div className="pnl-item">
          <span className="pnl-label">Net P&L:</span>
          <span className={`pnl-value ${isProfitable ? 'profit' : 'loss'}`}>
            ${pnl.netPnl?.toFixed(2) || '0.00'}
          </span>
        </div>
        
        <div className="pnl-item">
          <span className="pnl-label">Realized P&L:</span>
          <span className={`pnl-value ${pnl.realizedPnl > 0 ? 'profit' : pnl.realizedPnl < 0 ? 'loss' : ''}`}>
            ${pnl.realizedPnl?.toFixed(2) || '0.00'}
          </span>
        </div>
        
        <div className="pnl-item">
          <span className="pnl-label">Unrealized P&L:</span>
          <span className={`pnl-value ${pnl.unrealizedPnl > 0 ? 'profit' : pnl.unrealizedPnl < 0 ? 'loss' : ''}`}>
            ${pnl.unrealizedPnl?.toFixed(2) || '0.00'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default PnLDisplay;