from __future__ import annotations
import logging
import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for JSON-line structured logging to stdout."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Also configure stdlib logging to suppress noisy third-party logs
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    for noisy in ("uvicorn.access", "uvicorn.error", "asyncio", "ray"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
