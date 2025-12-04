import string
import random
from django.db import models
from django.utils import timezone


def generate_short_code(length=6):
    """Generate random alphanumeric code for shortened URLs."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


class URLMapping(models.Model):
    """Maps short codes to original URLs."""
    
    original_url = models.URLField(max_length=2048)
    short_code = models.CharField(max_length=16, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    access_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.short_code} -> {self.original_url[:50]}"

    def save(self, *args, **kwargs):
        if not self.short_code:
            # try a few times to get a unique code
            for _ in range(10):
                code = generate_short_code()
                if not URLMapping.objects.filter(short_code=code).exists():
                    self.short_code = code
                    break
            else:
                # fallback to longer code
                self.short_code = generate_short_code(length=10)
        super().save(*args, **kwargs)

    def increment_access_count(self):
        URLMapping.objects.filter(pk=self.pk).update(
            access_count=models.F('access_count') + 1
        )


class RateLimitRecord(models.Model):
    """
    Tracks request counts per IP for rate limiting (fixed window approach).
    """
    
    ip_address = models.CharField(max_length=45, unique=True, db_index=True)
    window_start = models.DateTimeField()
    request_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['ip_address', 'window_start']),
        ]

    def __str__(self):
        return f"{self.ip_address}: {self.request_count} reqs"

    @classmethod
    def check_and_increment(cls, ip_address, limit, window_seconds):
        """
        Check if request is allowed under the rate limit.
        Returns dict with allowed, remaining, retry_after, current_count.
        """
        now = timezone.now()
        
        record, created = cls.objects.get_or_create(
            ip_address=ip_address,
            defaults={'window_start': now, 'request_count': 0}
        )
        
        elapsed = (now - record.window_start).total_seconds()
        
        # reset window if expired
        if elapsed >= window_seconds:
            record.window_start = now
            record.request_count = 0
            elapsed = 0
        
        if record.request_count < limit:
            # atomic increment
            record.request_count = models.F('request_count') + 1
            record.save(update_fields=['window_start', 'request_count'])
            record.refresh_from_db()
            
            return {
                'allowed': True,
                'remaining': max(0, limit - record.request_count),
                'retry_after': 0,
                'current_count': record.request_count
            }
        
        # rate limited
        retry_after = max(1, int(window_seconds - elapsed))
        return {
            'allowed': False,
            'remaining': 0,
            'retry_after': retry_after,
            'current_count': record.request_count
        }
