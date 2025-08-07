import logging.config
import sys
import os
from loguru import logger
from model.utils.config import config

def setup_logger(env='development'):
    """Setup loguru logger with configuration from config.yml"""
    
    # Remove default loguru handler
    logger.remove()
    
    # Get logging configuration
    logging_config = config['logging']
    
    # Determine log level based on environment
    if env == 'development':
        log_level = "DEBUG"
        # Add console handler for development
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=log_level,
            colorize=True
        )
    elif env == 'production':
        log_level = "WARNING"
        # Ensure logs directory exists
        os.makedirs("logs", exist_ok=True)
        # Add file handler for production
        logger.add(
            "logs/app.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=log_level,
            rotation="10 MB",
            retention=10,
            compression="zip"
        )
    else:
        # Default: both console and file
        log_level = "INFO"
        os.makedirs("logs", exist_ok=True)
        
        # Console handler
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            colorize=True
        )
        
        # File handler
        logger.add(
            "logs/app.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO",
            rotation="10 MB",
            retention=10,
            compression="zip"
        )
    
    logger.info("Loguru logger setup complete for environment: {}", env)