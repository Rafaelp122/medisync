"""Rate-limited notification adapter decorator wrapping any NotificationPort."""

import logging

from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.infrastructure.notifications.rate_limiter import (
    NotificationRateLimiter,
)

logger: logging.Logger = logging.getLogger("medisync.queue.notifications")


class RateLimitedNotificationAdapter(NotificationPort):
    """Decorator wrapping any NotificationPort with token bucket rate limiting."""

    def __init__(
        self,
        delegate: NotificationPort,
        rate_limiter: NotificationRateLimiter,
    ) -> None:
        self._delegate = delegate
        self._rate_limiter = rate_limiter

    async def send_sms(self, to: str, message: str) -> bool:
        """Send SMS if not restricted by rate limiter."""
        res = await self._rate_limiter.check_rate_limit(to, cost=1)
        if not res.allowed:
            logger.warning(
                "SMS to %s rate-limited. Retry after %.2fs",
                to,
                res.retry_after_seconds,
            )
            return False
        return await self._delegate.send_sms(to, message)

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        """Send WhatsApp if not restricted by rate limiter."""
        res = await self._rate_limiter.check_rate_limit(to, cost=1)
        if not res.allowed:
            logger.warning(
                "WhatsApp to %s rate-limited. Retry after %.2fs",
                to,
                res.retry_after_seconds,
            )
            return False
        return await self._delegate.send_whatsapp(to, template, params)
