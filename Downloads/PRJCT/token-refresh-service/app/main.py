#!/usr/bin/env python3
import asyncio
import logging
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Set, Any

# Import our application modules
from .config import settings
from .database import init_db, test_db_connection
from .database.session import engine
from .database.utils import update_service_status, get_refresh_statistics
from .core.token_service import TokenService
from .utils.logging_config import setup_logging

# Setup logging
logger = setup_logging()

# Track running tasks
background_tasks: Set[asyncio.Task] = set()

# Initialize token service
token_service = TokenService()

# Signal handling
def handle_shutdown_signals():
    """Setup signal handlers for graceful shutdown"""
    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signum}. Starting graceful shutdown...")
        asyncio.create_task(shutdown())
    
    # Register handlers for common shutdown signals
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

async def shutdown():
    """Graceful shutdown procedure"""
    logger.info("Beginning service shutdown...")
    
    # Stop the token service
    await token_service.stop()
    
    # Cancel all running tasks
    for task in background_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    # Close database connections
    if engine:
        engine.dispose()
    
    logger.info("Service shutdown complete")
    # Exit process with success code
    sys.exit(0)

async def health_check() -> Dict[str, Any]:
    """Perform service health check"""
    # Check database connection
    db_connection = await test_db_connection()
    
    # Get refresh statistics
    refresh_stats = get_refresh_statistics()
    
    # Get token service status
    service_status = token_service.get_status()
    
    return {
        "status": "healthy" if db_connection and service_status.get("running", False) else "unhealthy",
        "timestamp": time.time(),
        "components": {
            "database": {
                "status": "connected" if db_connection else "disconnected"
            },
            "token_service": service_status,
            "refresh_statistics": refresh_stats
        }
    }

async def update_status_metrics():
    """Periodically update service status metrics"""
    try:
        while True:
            # Collect service metrics
            metrics = token_service.get_metrics()
            
            # Update metrics in database
            with token_service.get_db_session() as db:
                update_service_status(db, metrics)
            
            # Sleep for configured interval
            await asyncio.sleep(settings.STATUS_UPDATE_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Status update task cancelled")
    except Exception as e:
        logger.error(f"Error in status update task: {str(e)}")

async def run_health_check_endpoint():
    """Run a simple health check HTTP endpoint"""
    from aiohttp import web
    
    async def health_handler(request):
        """Handle health check requests"""
        health_data = await health_check()
        return web.json_response(health_data)
    
    app = web.Application()
    app.router.add_get('/health', health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Use port 8080 for health checks
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    logger.info("Health check endpoint running on http://0.0.0.0:8080/health")
    
    # Keep the server running
    while True:
        await asyncio.sleep(3600)  # Sleep for an hour

async def startup():
    """Initialize and start all service components"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION} in {settings.ENVIRONMENT} environment")
    
    try:
        # Initialize database
        logger.info("Initializing database...")
        init_db()
        
        # Test database connection
        db_connected = await test_db_connection()
        if not db_connected:
            logger.critical("Database connection failed - cannot start service")
            return False
        
        # Initialize token service
        logger.info("Initializing token service...")
        await token_service.initialize()
        
        # Start status monitoring
        logger.info("Starting status monitoring...")
        status_task = asyncio.create_task(update_status_metrics())
        background_tasks.add(status_task)
        
        # Start health check endpoint
        logger.info("Starting health check endpoint...")
        health_task = asyncio.create_task(run_health_check_endpoint())
        background_tasks.add(health_task)
        
        # Start token service
        logger.info("Starting token refresh service...")
        await token_service.start()
        
        logger.info(f"{settings.APP_NAME} started successfully")
        return True
        
    except Exception as e:
        logger.critical(f"Startup failed: {str(e)}")
        return False

async def main():
    """Main entry point for the service"""
    # Setup signal handlers
    handle_shutdown_signals()
    
    # Start the service
    success = await startup()
    if not success:
        logger.critical("Service failed to start properly")
        await shutdown()
        return
    
    try:
        # Keep the main task running
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
        await shutdown()

if __name__ == "__main__":
    # Run the main coroutine
    asyncio.run(main())