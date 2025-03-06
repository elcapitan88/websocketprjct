from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from sqlalchemy import event
import logging
import os
import contextlib
from typing import Generator

from ..config import settings

# Configure logger
logger = logging.getLogger(__name__)

# Base class for model definitions
Base = declarative_base()

# Configure database connection parameters with sensible defaults for a microservice
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))  # 30 minutes

# Create engine with connection pooling optimized for background worker
try:
    engine = create_engine(
        settings.DATABASE_URL,
        poolclass=QueuePool,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_timeout=DB_POOL_TIMEOUT,
        pool_recycle=DB_POOL_RECYCLE,
        pool_pre_ping=True,  # Verify connections before usage
        echo=settings.SQL_ECHO,
    )
    logger.info(f"Database engine created with pool_size={DB_POOL_SIZE}, max_overflow={DB_MAX_OVERFLOW}")
except Exception as e:
    logger.critical(f"Failed to create database engine: {str(e)}")
    raise

# Add event listeners for connection monitoring
@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    logger.debug("Database connection established")

@event.listens_for(engine, "checkout")
def checkout(dbapi_connection, connection_record, connection_proxy):
    logger.debug("Database connection checked out from pool")

@event.listens_for(engine, "checkin")
def checkin(dbapi_connection, connection_record):
    logger.debug("Database connection returned to pool")

# Create scoped session factory - thread-safe for background workers
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
)

# Context manager for database sessions
@contextlib.contextmanager
def get_db() -> Generator:
    """
    Context manager for database sessions with error handling and automatic rollback
    """
    db = SessionLocal()
    try:
        logger.debug("Opening new database session")
        yield db
    except Exception as e:
        logger.error(f"Exception during database session: {str(e)}")
        db.rollback()
        raise
    finally:
        logger.debug("Closing database session")
        db.close()

# Function to test database connection
async def test_db_connection() -> bool:
    """Test if database connection is working"""
    try:
        with get_db() as db:
            # Execute simple query
            db.execute("SELECT 1")
            logger.info("Database connection test successful")
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {str(e)}")
        return False

# Function to initialize database
def init_db() -> None:
    """Create all tables if they don't exist"""
    try:
        # Import all models here
        from .models import BrokerCredentials, BrokerAccount
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise