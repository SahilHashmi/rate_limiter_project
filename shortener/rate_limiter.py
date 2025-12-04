"""
Custom rate limiter using fixed window algorithm.
Stores counters in the database - for higher scale, swap to Redis.
"""
from dataclasses import dataclass
from django.conf import settings
from .models import RateLimitRecord


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int
    limit: int
    window_seconds: int


def get_client_ip(request):
    """Get client IP, handling proxies."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def check_rate_limit(request, limit=None, window_seconds=None):
    """
    Check if request is within rate limits.
    Uses fixed window counter stored in DB.
    """
    if limit is None:
        limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 5)
    if window_seconds is None:
        window_seconds = getattr(settings, 'RATE_LIMIT_WINDOW_SECONDS', 60)
    
    ip = get_client_ip(request)
    result = RateLimitRecord.check_and_increment(ip, limit, window_seconds)
    
    return RateLimitResult(
        allowed=result['allowed'],
        remaining=result['remaining'],
        retry_after=result['retry_after'],
        limit=limit,
        window_seconds=window_seconds
    )


def get_rate_limit_headers(result):
    """Build rate limit headers for response."""
    headers = {
        'X-RateLimit-Limit': str(result.limit),
        'X-RateLimit-Remaining': str(result.remaining),
        'X-RateLimit-Reset': str(result.window_seconds),
    }
    if not result.allowed:
        headers['Retry-After'] = str(result.retry_after)
    return headers
