"""
Structured Logging Configuration

Uses structlog for better log analysis and debugging
"""

import structlog
import logging
from datetime import datetime


def setup_structured_logging():
    """
    Configure structured logging with JSON output
    
    Benefits:
    - Easier to parse and analyze
    - Better for log aggregation tools
    - Consistent format across all logs
    """
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Initialize on import
setup_structured_logging()


def get_logger(name: str):
    """Get a structured logger instance"""
    return structlog.get_logger(name)