from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any, Optional

from .models import BrokerAccount, BrokerCredentials, RefreshAttempt, ServiceStatus

logger = logging.getLogger(__name__)

# Token query functions
def get_expiring_credentials(
    db: Session, 
    minutes_threshold: int, 
    limit: int = 100
) -> List[BrokerCredentials]:
    """
    Get credentials that will expire within the specified minutes threshold
    
    Args:
        db: Database session
        minutes_threshold: Minutes until token expiration
        limit: Maximum number of records to return
        
    Returns:
        List of BrokerCredentials objects
    """
    expiry_threshold = datetime.utcnow() + timedelta(minutes=minutes_threshold)
    
    return db.query(BrokerCredentials).join(
        BrokerAccount, 
        BrokerCredentials.account_id == BrokerAccount.id
    ).filter(
        BrokerCredentials.is_valid == True,
        BrokerCredentials.expires_at <= expiry_threshold,
        BrokerAccount.is_active == True,
        BrokerAccount.is_deleted == False
    ).order_by(
        BrokerCredentials.expires_at
    ).limit(limit).all()


def get_credentials_by_tier(db: Session, tier: str, limit: int = 100) -> List[BrokerCredentials]:
    """
    Get credentials by refresh urgency tier
    
    Args:
        db: Database session
        tier: One of 'urgent', 'soon', 'normal'
        limit: Maximum number of records to return
        
    Returns:
        List of BrokerCredentials objects
    """
    now = datetime.utcnow()
    
    if tier == 'urgent':
        # Tokens expiring within 10 minutes
        threshold = now + timedelta(minutes=10)
        return get_expiring_credentials(db, 10, limit)
    
    elif tier == 'soon':
        # Tokens expiring between 10 and 30 minutes
        start_threshold = now + timedelta(minutes=10)
        end_threshold = now + timedelta(minutes=30)
        
        return db.query(BrokerCredentials).join(
            BrokerAccount, 
            BrokerCredentials.account_id == BrokerAccount.id
        ).filter(
            BrokerCredentials.is_valid == True,
            BrokerCredentials.expires_at > start_threshold,
            BrokerCredentials.expires_at <= end_threshold,
            BrokerAccount.is_active == True,
            BrokerAccount.is_deleted == False
        ).order_by(
            BrokerCredentials.expires_at
        ).limit(limit).all()
    
    else:  # 'normal' tier
        # All valid tokens not in urgent or soon tiers
        threshold = now + timedelta(minutes=30)
        
        return db.query(BrokerCredentials).join(
            BrokerAccount, 
            BrokerCredentials.account_id == BrokerAccount.id
        ).filter(
            BrokerCredentials.is_valid == True,
            BrokerCredentials.expires_at > threshold,
            BrokerAccount.is_active == True,
            BrokerAccount.is_deleted == False
        ).order_by(
            BrokerCredentials.expires_at
        ).limit(limit).all()


def log_refresh_attempt(
    db: Session,
    credential_id: int,
    success: bool,
    error_message: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    scheduled_tier: Optional[str] = None,
    refresh_method: Optional[str] = None
) -> RefreshAttempt:
    """
    Log a token refresh attempt
    
    Args:
        db: Database session
        credential_id: ID of the credential being refreshed
        success: Whether the refresh was successful
        error_message: Error message if refresh failed
        response_time_ms: Response time in milliseconds
        scheduled_tier: Tier that scheduled this refresh
        refresh_method: Method used for refresh
        
    Returns:
        Created RefreshAttempt object
    """
    try:
        refresh_attempt = RefreshAttempt(
            credential_id=credential_id,
            success=success,
            error_message=error_message,
            response_time_ms=response_time_ms,
            scheduled_tier=scheduled_tier,
            refresh_method=refresh_method
        )
        
        db.add(refresh_attempt)
        db.commit()
        db.refresh(refresh_attempt)
        
        return refresh_attempt
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log refresh attempt: {str(e)}")
        # Return a non-persisted object
        return RefreshAttempt(
            credential_id=credential_id,
            success=success,
            error_message=f"Failed to log attempt: {str(e)}"
        )


def update_service_status(
    db: Session,
    status_data: Dict[str, Any]
) -> ServiceStatus:
    """
    Update service status metrics
    
    Args:
        db: Database session
        status_data: Dictionary of status metrics
        
    Returns:
        Created ServiceStatus object
    """
    try:
        status = ServiceStatus(**status_data)
        
        db.add(status)
        db.commit()
        db.refresh(status)
        
        return status
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update service status: {str(e)}")
        # Return a non-persisted object
        return ServiceStatus(
            status="error",
            error_message=f"Failed to update status: {str(e)}"
        )


def get_refresh_statistics(db: Session, hours: int = 24) -> Dict[str, Any]:
    """
    Get token refresh statistics for the specified time period
    
    Args:
        db: Database session
        hours: Number of hours to look back
        
    Returns:
        Dictionary of statistics
    """
    start_time = datetime.utcnow() - timedelta(hours=hours)
    
    try:
        # Get total attempts
        total_attempts = db.query(func.count(RefreshAttempt.id)).filter(
            RefreshAttempt.attempted_at >= start_time
        ).scalar() or 0
        
        # Get successful attempts
        successful_attempts = db.query(func.count(RefreshAttempt.id)).filter(
            RefreshAttempt.attempted_at >= start_time,
            RefreshAttempt.success == True
        ).scalar() or 0
        
        # Get failed attempts
        failed_attempts = db.query(func.count(RefreshAttempt.id)).filter(
            RefreshAttempt.attempted_at >= start_time,
            RefreshAttempt.success == False
        ).scalar() or 0
        
        # Get average response time
        avg_response_time = db.query(func.avg(RefreshAttempt.response_time_ms)).filter(
            RefreshAttempt.attempted_at >= start_time,
            RefreshAttempt.response_time_ms.isnot(None)
        ).scalar() or 0
        
        # Get distribution by tier
        tier_counts = {}
        for tier in ['urgent', 'soon', 'normal']:
            count = db.query(func.count(RefreshAttempt.id)).filter(
                RefreshAttempt.attempted_at >= start_time,
                RefreshAttempt.scheduled_tier == tier
            ).scalar() or 0
            tier_counts[tier] = count
        
        # Return statistics
        return {
            "period_hours": hours,
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": (successful_attempts / total_attempts * 100) if total_attempts > 0 else 0,
            "avg_response_time_ms": round(avg_response_time, 2),
            "tier_distribution": tier_counts
        }
    except Exception as e:
        logger.error(f"Failed to get refresh statistics: {str(e)}")
        return {
            "error": str(e),
            "period_hours": hours
        }