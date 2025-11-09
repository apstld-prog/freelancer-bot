import logging
from datetime import datetime, timezone

logger = logging.getLogger("platform.placeholders")


async def fetch_placeholder_jobs(keywords: list[str]):
    """
    Generic fallback loader when a platform is disabled or placeholder.
    Always returns an empty list.
    """
    logger.info("Placeholder platform called — returning no jobs.")
    return []


