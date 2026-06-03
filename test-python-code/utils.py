import logging
from datetime import datetime

logger = logging.getLogger("sentinel")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def log_analysis_event(service_name: str, status: str):
    """Log each analysis event for audit trail."""
    logger.info(f"Analysis completed | service={service_name} | status={status}")


def get_timestamp() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()
