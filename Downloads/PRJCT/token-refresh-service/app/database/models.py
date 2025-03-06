from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import relationship
from datetime import datetime

from .session import Base

class BrokerAccount(Base):
    """Minimal model for broker accounts - only includes fields needed for token refresh"""
    __tablename__ = "broker_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    broker_id = Column(String(50), nullable=False)  # e.g., "tradovate"
    account_id = Column(String, unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    nickname = Column(String(200), nullable=True)
    environment = Column(String(10), nullable=False)  # demo, live, etc.
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default='inactive')
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_connected = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)

    # Relationship to credentials
    credentials = relationship("BrokerCredentials", back_populates="account", uselist=False)

    def __repr__(self):
        return f"<BrokerAccount {self.broker_id}:{self.account_id} ({self.status})>"


class BrokerCredentials(Base):
    """Model for storing broker authentication credentials - central to token refresh service"""
    __tablename__ = "broker_credentials"

    id = Column(Integer, primary_key=True, index=True)
    broker_id = Column(String(50), nullable=False)
    account_id = Column(Integer, ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    credential_type = Column(String(20), nullable=False)  # oauth, api_key, etc.
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_valid = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    refresh_fail_count = Column(Integer, default=0)
    last_refresh_attempt = Column(DateTime, nullable=True)
    last_refresh_error = Column(String, nullable=True)
    error_message = Column(String, nullable=True)

    # Relationship to broker account
    account = relationship("BrokerAccount", back_populates="credentials")

    def __repr__(self):
        return f"<BrokerCredentials {self.id} ({self.broker_id})>"
    
    def to_dict(self):
        """Convert instance to dictionary for API responses"""
        return {
            "id": self.id,
            "broker_id": self.broker_id,
            "credential_type": self.credential_type,
            "is_valid": self.is_valid,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "refresh_fail_count": self.refresh_fail_count,
            "last_refresh_attempt": self.last_refresh_attempt.isoformat() if self.last_refresh_attempt else None,
            "last_refresh_error": self.last_refresh_error
        }


class RefreshAttempt(Base):
    """Model to log token refresh attempts for monitoring and analytics"""
    __tablename__ = "token_refresh_attempts"

    id = Column(Integer, primary_key=True, index=True)
    credential_id = Column(Integer, ForeignKey("broker_credentials.id", ondelete="CASCADE"))
    attempted_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    response_time_ms = Column(Integer, nullable=True)  # Response time in milliseconds
    scheduled_tier = Column(String(20), nullable=True)  # urgent, soon, normal
    refresh_method = Column(String(30), nullable=True)  # Method used for refresh
    
    def __repr__(self):
        result = "Success" if self.success else "Failed"
        return f"<RefreshAttempt {self.id} ({result})>"


class ServiceStatus(Base):
    """Model to track service uptime and health metrics"""
    __tablename__ = "token_service_status"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String(20), default="running")  # running, degraded, stopped
    active_tokens = Column(Integer, default=0)
    expired_tokens = Column(Integer, default=0)
    refresh_success_count = Column(Integer, default=0)
    refresh_fail_count = Column(Integer, default=0)
    urgent_queue_size = Column(Integer, default=0)
    soon_queue_size = Column(Integer, default=0)
    normal_queue_size = Column(Integer, default=0)
    cpu_usage = Column(Integer, nullable=True)  # Percentage
    memory_usage = Column(Integer, nullable=True)  # MB
    
    def __repr__(self):
        return f"<ServiceStatus {self.id} ({self.status})>"


# Import these models in other files using:
# from app.database.models import BrokerAccount, BrokerCredentials, RefreshAttempt, ServiceStatus