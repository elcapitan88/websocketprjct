import React from 'react';

const PositionsList = ({ positions }) => {
  // If positions array is empty or not provided
  if (!positions || positions.length === 0) {
    return (
      <div className="card positions-list">
        <h2>Positions</h2>
        <p>No active positions.</p>
      </div>
    );
  }

  return (
    <div className="card positions-list">
      <h2>Positions</h2>
      <div className="positions-table-container">
        <table className="positions-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Quantity</th>
              <th>Entry Price</th>
              <th>Current Price</th>
              <th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((position, index) => (
              <tr key={position.id || index} className={position.pnl > 0 ? 'profit' : position.pnl < 0 ? 'loss' : ''}>
                <td>{position.symbol}</td>
                <td>{position.netPos}</td>
                <td>${position.entryPrice?.toFixed(2) || 'N/A'}</td>
                <td>${position.marketPrice?.toFixed(2) || 'N/A'}</td>
                <td className={position.pnl > 0 ? 'profit' : position.pnl < 0 ? 'loss' : ''}>
                  ${position.pnl?.toFixed(2) || '0.00'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default PositionsList;