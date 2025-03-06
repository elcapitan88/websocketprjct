# app/core/token_service.py
import asyncio
import logging
import time
import traceback
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings, TokenConfig
from app.database.session import get_db_context

logger = logging.getLogger("token-refresh-service")

class TokenRefreshError(Exception):
    """Exception raised for token refresh errors"""
    pass

class TokenService:
    """
    Core service for managing broker token refresh operations.
    This standalone service focuses exclusively on keeping tokens valid.
    """
    
    def __init__(self):
        """Initialize token service with required components"""
        self._locks: Dict[str, asyncio.Lock] = {}
        self._refresh_attempts: Dict[str, int] = {}
        self._refresh_in_progress: Set[str] = set()
        self._client = httpx.AsyncClient(timeout=30.0)
        self._last_metrics_update = datetime.utcnow()
        self._refresh_metrics = {
            "total_processed": 0,
            "successful_refreshes": 0,
            "failed_refreshes": 0,
            "invalid_tokens": 0
        }
        logger.info("Token service initialized")
    
    async def close(self):
        """Close resources"""
        await self._client.aclose()
        logger.info("Token service resources closed")
    
    async def get_lock(self, credential_id: str) -> asyncio.Lock:
        """Get or create a lock for a specific credential"""
        if credential_id not in self._locks:
            self._locks[credential_id] = asyncio.Lock()
        return self._locks[credential_id]
    
    def _get_refresh_attempts(self, credential_id: str) -> int:
        """Get current refresh attempts for a credential"""
        return self._refresh_attempts.get(credential_id, 0)
    
    def _increment_refresh_attempts(self, credential_id: str):
        """Increment refresh attempts counter"""
        self._refresh_attempts[credential_id] = self._get_refresh_attempts(credential_id) + 1
        logger.info(f"Incremented refresh attempts for credential {credential_id} to {self._refresh_attempts[credential_id]}")
    
    def _reset_refresh_attempts(self, credential_id: str):
        """Reset refresh attempts counter"""
        if credential_id in self._refresh_attempts:
            del self._refresh_attempts[credential_id]
            logger.info(f"Reset refresh attempts for credential {credential_id}")
    
    async def get_active_credentials(self, tier: str = "all") -> List[Dict[str, Any]]:
        """
        Find active credentials that may need refresh based on tier level.
        Optimized for 60-80 minute tokens.
        
        Tiers:
        - urgent: Tokens expiring within 10 minutes
        - soon: Tokens expiring in 10-20 minutes
        - all: All valid tokens (full scan)
        
        Returns a list of credential records.
        """
        try:
            with get_db_context() as db:
                # Base query components
                select_clause = """
                SELECT bc.id, bc.broker_id, bc.account_id, bc.access_token, 
                       bc.expires_at, bc.is_valid, bc.created_at, bc.updated_at,
                       bc.refresh_fail_count, bc.last_refresh_attempt, bc.last_refresh_error,
                       ba.environment, ba.is_active, ba.status, ba.account_id as broker_account_id
                FROM broker_credentials bc
                JOIN broker_accounts ba ON bc.account_id = ba.id
                WHERE bc.is_valid = true AND ba.is_active = true AND ba.deleted_at IS NULL
                """
                
                # Add tier-specific expiration filter
                current_time = datetime.utcnow()
                if tier == "urgent":
                    # Tokens expiring within 10 minutes (~12-15% of lifetime)
                    expires_before = current_time + timedelta(minutes=10)
                    where_clause = f" AND bc.expires_at <= '{expires_before}'"
                    limit_clause = " LIMIT 100"  # Process urgent ones in smaller batches
                elif tier == "soon":
                    # Tokens expiring in 10-20 minutes (25-30% of lifetime)
                    urgent_threshold = current_time + timedelta(minutes=10)
                    soon_threshold = current_time + timedelta(minutes=20)
                    where_clause = f" AND bc.expires_at > '{urgent_threshold}' AND bc.expires_at <= '{soon_threshold}'"
                    limit_clause = " LIMIT 200"
                else:
                    # All valid tokens
                    where_clause = ""
                    limit_clause = " LIMIT 500"  # Reasonable batch size for full scan
                
                # Order by expiration time (most urgent first)
                order_clause = " ORDER BY bc.expires_at ASC"
                
                # Complete query
                query = select_clause + where_clause + order_clause + limit_clause
                
                # Execute query directly for better performance
                result = db.execute(query)
                
                # Convert to list of dictionaries
                credentials = []
                for row in result:
                    # Convert SQLAlchemy row to dict
                    credential = {column: value for column, value in zip(result.keys(), row)}
                    
                    # Add calculated fields
                    expires_at = credential['expires_at']
                    if expires_at:
                        credential['seconds_until_expiry'] = (expires_at - current_time).total_seconds()
                    else:
                        credential['seconds_until_expiry'] = 0
                    
                    # Add tier info for logging
                    credential['refresh_tier'] = tier
                        
                    credentials.append(credential)
                
                logger.debug(f"Found {len(credentials)} active credentials in {tier} tier")
                return credentials
                    
        except Exception as e:
            logger.error(f"Error getting active credentials: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    async def refresh_token_if_needed(self, credential: Dict[str, Any]) -> bool:
        """
        Refresh token with proper locking and transaction handling.
        Returns True if refresh was successful or not needed.
        """
        credential_id = str(credential['id'])
        broker_id = credential['broker_id']
        broker_config = TokenConfig.get_broker_config(broker_id)
        lock = await self.get_lock(credential_id)
        
        # Skip if this credential is already being processed
        if credential_id in self._refresh_in_progress:
            logger.debug(f"Skipping credential {credential_id} - refresh already in progress")
            return True
        
        try:
            # Use timeout to prevent deadlocks
            async with asyncio.timeout(settings.LOCK_TIMEOUT):
                async with lock:
                    self._refresh_in_progress.add(credential_id)
                    try:
                        # Check if refresh is actually needed based on broker-specific threshold
                        seconds_until_expiry = credential['seconds_until_expiry']
                        refresh_threshold = broker_config['REFRESH_THRESHOLD']
                        token_lifetime = broker_config['TOKEN_LIFETIME']
                        refresh_threshold_seconds = refresh_threshold * token_lifetime
                        
                        logger.info(
                            f"Credential {credential_id} ({broker_id}) expires in {seconds_until_expiry:.0f} seconds. "
                            f"Refresh threshold: {refresh_threshold_seconds:.0f} seconds"
                        )
                        
                        # If token is still valid for longer than the threshold, no refresh needed
                        if seconds_until_expiry > refresh_threshold_seconds:
                            logger.debug(f"No refresh needed for credential {credential_id}")
                            return True
                        
                        # Check if we've exceeded max retry attempts
                        if self._get_refresh_attempts(credential_id) >= broker_config['MAX_RETRY_ATTEMPTS']:
                            await self._handle_max_retries_exceeded(credential_id, credential)
                            return False
                        
                        # Let's refresh the token
                        logger.info(f"Starting refresh for credential {credential_id} (broker: {broker_id}, environment: {credential['environment']})")
                        
                        # Refresh based on broker type - for now just Tradovate
                        if broker_id.lower() == 'tradovate':
                            success = await self._refresh_tradovate_token(credential)
                        else:
                            logger.error(f"Unsupported broker type: {broker_id}")
                            return False
                        
                        if success:
                            self._reset_refresh_attempts(credential_id)
                            self._refresh_metrics["successful_refreshes"] += 1
                            logger.info(f"Successfully refreshed token for credential {credential_id}")
                            return True
                        else:
                            self._increment_refresh_attempts(credential_id)
                            self._refresh_metrics["failed_refreshes"] += 1
                            logger.error(f"Failed to refresh token for credential {credential_id}")
                            return False
                    
                    finally:
                        self._refresh_in_progress.remove(credential_id)
        
        except asyncio.TimeoutError:
            logger.error(f"Lock acquisition timeout for credential {credential_id}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in token refresh for credential {credential_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _refresh_tradovate_token(self, credential: Dict[str, Any]) -> bool:
        """
        Tradovate-specific token refresh implementation
        Returns True if successful, False otherwise
        """
        try:
            # Get the right renew URL based on environment
            environment = credential['environment']
            renew_url = settings.get_broker_urls('tradovate', environment)['renew_token_url']
            access_token = credential['access_token']
            
            if not renew_url or not access_token:
                logger.error(f"Missing necessary data for token refresh: URL or token")
                return False
            
            # Prepare headers with existing token
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}'
            }
            
            # Make token renewal request
            logger.debug(f"Sending token refresh request to {renew_url}")
            response = await self._client.post(
                renew_url,
                headers=headers
            )
            
            # Check for successful response
            if response.status_code != 200:
                logger.error(f"Token refresh failed with status {response.status_code}: {response.text}")
                return False
            
            # Parse response
            refresh_data = response.json()
            logger.debug(f"Token refresh response: {json.dumps(refresh_data)}")
            
            if 'accessToken' not in refresh_data or 'expirationTime' not in refresh_data:
                logger.error(f"Invalid token refresh response: {json.dumps(refresh_data)}")
                return False
            
            # Update token in database
            with get_db_context() as db:
                # Update the credential with new token information
                update_query = """
                UPDATE broker_credentials
                SET access_token = :access_token,
                    expires_at = :expires_at,
                    is_valid = true,
                    refresh_fail_count = 0,
                    last_refresh_attempt = :refresh_time,
                    last_refresh_error = NULL,
                    updated_at = :refresh_time
                WHERE id = :id
                """
                
                # Parse ISO format date with timezone
                expiration_time = datetime.fromisoformat(refresh_data['expirationTime'].replace('Z', '+00:00'))
                
                # Execute update
                db.execute(
                    update_query,
                    {
                        'access_token': refresh_data['accessToken'],
                        'expires_at': expiration_time,
                        'refresh_time': datetime.utcnow(),
                        'id': credential['id']
                    }
                )
                
                db.commit()
                logger.info(f"Token updated in database for credential {credential['id']}, new expiry: {expiration_time}")
                
                return True
                
        except httpx.RequestError as e:
            logger.error(f"HTTP request error during token refresh: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error refreshing Tradovate token: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    async def _handle_max_retries_exceeded(self, credential_id: str, credential: Dict[str, Any]):
        """Handle case when max refresh retries are exceeded"""
        logger.error(f"Max refresh attempts exceeded for credential {credential_id}")
        
        try:
            with get_db_context() as db:
                # Update credential status
                db.execute(
                    """
                    UPDATE broker_credentials
                    SET is_valid = false,
                        last_refresh_error = 'Max refresh attempts exceeded',
                        updated_at = :updated_at
                    WHERE id = :id
                    """,
                    {
                        'id': credential_id,
                        'updated_at': datetime.utcnow()
                    }
                )
                
                # Update associated account
                db.execute(
                    """
                    UPDATE broker_accounts
                    SET status = 'token_expired'
                    WHERE id = :account_id
                    """,
                    {
                        'account_id': credential['account_id']
                    }
                )
                
                db.commit()
                logger.info(f"Marked credential {credential_id} as invalid after max retries")
                self._refresh_metrics["invalid_tokens"] += 1
                
        except Exception as e:
            logger.error(f"Error handling max retries: {str(e)}")
    
    async def _update_metrics(self):
        """Update and log service metrics"""
        now = datetime.utcnow()
        elapsed = (now - self._last_metrics_update).total_seconds()
        
        if elapsed >= 300:  # Log every 5 minutes
            logger.info(f"Refresh Metrics: {json.dumps(self._refresh_metrics)}")
            
            with get_db_context() as db:
                # Get some stats from the database
                stats = db.execute(
                    """
                    SELECT 
                        COUNT(*) as total_credentials,
                        SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid_credentials,
                        SUM(CASE WHEN refresh_fail_count > 0 THEN 1 ELSE 0 END) as failing_credentials
                    FROM broker_credentials
                    """
                ).fetchone()
                
                if stats:
                    logger.info(f"Database stats: Total credentials: {stats[0]}, Valid: {stats[1]}, Failing: {stats[2]}")
            
            self._last_metrics_update = now
    
    async def run_refresh_cycle(self):
        """
        Run a complete token refresh cycle with tiered scheduling.
        Processes tokens in order of urgency.
        """
        try:
            cycle_start = time.time()
            
            # Determine which tiers to check this cycle
            current_minute = datetime.utcnow().minute
            check_urgent = True  # Always check urgent tokens (< 10 min to expiry)
            check_soon = current_minute % 5 == 0  # Check soon tokens every 5 minutes
            check_all = current_minute % 30 == 0  # Full scan every 30 minutes
            
            total_processed = 0
            total_refreshed = 0
            
            # Process urgent tier (tokens expiring within 10 minutes)
            if check_urgent:
                urgent_credentials = await self.get_active_credentials(tier="urgent")
                if urgent_credentials:
                    logger.info(f"Processing {len(urgent_credentials)} urgent credentials")
                    total_processed += len(urgent_credentials)
                    
                    # Process urgent credentials with high priority
                    tasks = [self.refresh_token_if_needed(credential) for credential in urgent_credentials]
                    results = await asyncio.gather(*tasks)
                    
                    refreshed = sum(1 for r in results if r)
                    total_refreshed += refreshed
                    logger.info(f"Urgent tier complete: {refreshed}/{len(urgent_credentials)} refreshed")
            
            # Process soon tier (tokens expiring within 20 minutes)
            if check_soon:
                soon_credentials = await self.get_active_credentials(tier="soon")
                if soon_credentials:
                    logger.info(f"Processing {len(soon_credentials)} soon-to-expire credentials")
                    total_processed += len(soon_credentials)
                    
                    # Process in batches
                    batch_size = TokenConfig.MAX_TOKENS_PER_BATCH
                    for i in range(0, len(soon_credentials), batch_size):
                        batch = soon_credentials[i:i+batch_size]
                        tasks = [self.refresh_token_if_needed(credential) for credential in batch]
                        results = await asyncio.gather(*tasks)
                        
                        refreshed = sum(1 for r in results if r)
                        total_refreshed += refreshed
                    
                    logger.info(f"Soon tier complete: {total_refreshed}/{len(soon_credentials)} refreshed")
            
            # Full scan for all tokens
            if check_all:
                all_credentials = await self.get_active_credentials(tier="all")
                if all_credentials:
                    logger.info(f"Performing full scan of {len(all_credentials)} credentials")
                    total_processed += len(all_credentials)
                    
                    # Process in larger batches
                    batch_size = TokenConfig.MAX_TOKENS_PER_BATCH
                    for i in range(0, len(all_credentials), batch_size):
                        batch = all_credentials[i:i+batch_size]
                        tasks = [self.refresh_token_if_needed(credential) for credential in batch]
                        results = await asyncio.gather(*tasks)
                        
                        refreshed = sum(1 for r in results if r)
                        total_refreshed += refreshed
                    
                    logger.info(f"Full scan complete: {total_refreshed}/{len(all_credentials)} refreshed")
            
            # Update metrics
            self._refresh_metrics["total_processed"] += total_processed
            await self._update_metrics()
            
            # Log cycle summary
            cycle_duration = time.time() - cycle_start
            logger.info(f"Refresh cycle completed in {cycle_duration:.2f}s: {total_processed} processed, {total_refreshed} refreshed")
            
        except Exception as e:
            logger.error(f"Error in refresh cycle: {str(e)}")
            logger.error(traceback.format_exc())
    
    async def run_until_shutdown(self, shutdown_event: asyncio.Event):
        """Run the token refresh service until shutdown is requested"""
        try:
            logger.info(f"Token refresh service starting with interval: {settings.REFRESH_INTERVAL}s")
            
            while not shutdown_event.is_set():
                cycle_start = time.time()
                
                # Run a refresh cycle
                await self.run_refresh_cycle()
                
                # Calculate sleep time (accounting for cycle duration)
                cycle_duration = time.time() - cycle_start
                sleep_time = max(1, settings.REFRESH_INTERVAL - cycle_duration)
                
                # Sleep until next cycle or until shutdown requested
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=sleep_time)
                except asyncio.TimeoutError:
                    # Normal timeout, continue with next cycle
                    pass
            
            logger.info("Shutdown event received, stopping token refresh service")
            
        except Exception as e:
            logger.error(f"Fatal error in token refresh service: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        finally:
            await self.close()