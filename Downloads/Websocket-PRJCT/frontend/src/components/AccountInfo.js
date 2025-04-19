import React from 'react';

const AccountInfo = ({ account }) => {
  if (!account) {
    return (
      <div className="card account-info">
        <p>No account information available.</p>
      </div>
    );
  }

  return (
    <div className="card account-info">
      <h2>Account Information</h2>
      <div className="account-details">
        <p>
          <strong>Account Name:</strong> {account.name || 'N/A'}
        </p>
        <p>
          <strong>Account ID:</strong> {account.id || 'N/A'}
        </p>
        <p>
          <strong>Status:</strong>{' '}
          <span className={`status ${account.status ? 'active' : 'inactive'}`}>
            {account.status ? 'Active' : 'Inactive'}
          </span>
        </p>
      </div>
    </div>
  );
};

export default AccountInfo;