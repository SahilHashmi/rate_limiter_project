"""
Comprehensive tests for URL Shortener Service.

Tests cover:
- URL shortening endpoint
- Redirect endpoint
- Rate limiting functionality
- Error handling
- Edge cases
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch
from datetime import timedelta
from django.utils import timezone

from .models import URLMapping, RateLimitRecord


class URLMappingModelTests(TestCase):
    """Tests for URLMapping model."""

    def test_create_url_mapping_generates_short_code(self):
        """Short code is auto-generated when not provided."""
        mapping = URLMapping.objects.create(
            original_url="https://example.com/test"
        )
        self.assertIsNotNone(mapping.short_code)
        self.assertEqual(len(mapping.short_code), 6)

    def test_short_code_is_unique(self):
        """Each URL mapping has a unique short code."""
        mapping1 = URLMapping.objects.create(original_url="https://example.com/1")
        mapping2 = URLMapping.objects.create(original_url="https://example.com/2")
        self.assertNotEqual(mapping1.short_code, mapping2.short_code)

    def test_increment_access_count(self):
        """Access count increments correctly."""
        mapping = URLMapping.objects.create(original_url="https://example.com")
        self.assertEqual(mapping.access_count, 0)
        
        mapping.increment_access_count()
        mapping.refresh_from_db()
        self.assertEqual(mapping.access_count, 1)

    def test_custom_short_code_preserved(self):
        """Custom short code is preserved when provided."""
        mapping = URLMapping.objects.create(
            original_url="https://example.com",
            short_code="custom1"
        )
        self.assertEqual(mapping.short_code, "custom1")


class RateLimitRecordModelTests(TestCase):
    """Tests for RateLimitRecord model."""

    def test_check_and_increment_allows_under_limit(self):
        """Requests under limit are allowed."""
        result = RateLimitRecord.check_and_increment(
            ip_address="192.168.1.1",
            limit=5,
            window_seconds=60
        )
        self.assertTrue(result['allowed'])
        self.assertEqual(result['current_count'], 1)

    def test_check_and_increment_blocks_over_limit(self):
        """Requests over limit are blocked."""
        ip = "192.168.1.2"
        
        # Make 5 requests (should all be allowed)
        for i in range(5):
            result = RateLimitRecord.check_and_increment(
                ip_address=ip, limit=5, window_seconds=60
            )
            self.assertTrue(result['allowed'])
        
        # 6th request should be blocked
        result = RateLimitRecord.check_and_increment(
            ip_address=ip, limit=5, window_seconds=60
        )
        self.assertFalse(result['allowed'])
        self.assertGreater(result['retry_after'], 0)

    def test_window_reset_allows_new_requests(self):
        """After window expires, new requests are allowed."""
        ip = "192.168.1.3"
        
        # Create a record with expired window
        old_time = timezone.now() - timedelta(seconds=120)
        record = RateLimitRecord.objects.create(
            ip_address=ip,
            window_start=old_time,
            request_count=5
        )
        
        # New request should be allowed (window expired)
        result = RateLimitRecord.check_and_increment(
            ip_address=ip, limit=5, window_seconds=60
        )
        self.assertTrue(result['allowed'])


class ShortenURLViewTests(APITestCase):
    """Tests for POST /shorten endpoint."""

    def test_shorten_valid_url(self):
        """Valid URL returns short code."""
        response = self.client.post(
            '/shorten',
            {'url': 'https://www.example.com/path'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('short_code', response.data)
        self.assertIn('short_url', response.data)
        self.assertIn('original_url', response.data)

    def test_shorten_invalid_url(self):
        """Invalid URL returns 400 error."""
        response = self.client.post(
            '/shorten',
            {'url': 'not-a-valid-url'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_shorten_missing_url(self):
        """Missing URL field returns 400 error."""
        response = self.client.post('/shorten', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_shorten_empty_body(self):
        """Empty request body returns 400 error."""
        response = self.client.post(
            '/shorten',
            None,
            format='json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rate_limit_headers_present(self):
        """Rate limit headers are included in response."""
        response = self.client.post(
            '/shorten',
            {'url': 'https://example.com'},
            format='json'
        )
        self.assertIn('X-RateLimit-Limit', response)
        self.assertIn('X-RateLimit-Remaining', response)
        self.assertIn('X-RateLimit-Reset', response)

    @override_settings(RATE_LIMIT_REQUESTS=3, RATE_LIMIT_WINDOW_SECONDS=60)
    def test_rate_limit_exceeded(self):
        """Rate limit returns 429 after limit exceeded."""
        # Clear any existing rate limit records
        RateLimitRecord.objects.all().delete()
        
        # Make requests up to limit
        for i in range(3):
            response = self.client.post(
                '/shorten',
                {'url': f'https://example.com/{i}'},
                format='json'
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Next request should be rate limited
        response = self.client.post(
            '/shorten',
            {'url': 'https://example.com/blocked'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Retry-After', response)
        self.assertIn('error', response.data)
        self.assertIn('retry_after', response.data)


class RedirectViewTests(APITestCase):
    """Tests for GET /{short_code} endpoint."""

    def test_redirect_valid_code(self):
        """Valid short code redirects to original URL."""
        mapping = URLMapping.objects.create(
            original_url="https://www.google.com"
        )
        response = self.client.get(f'/{mapping.short_code}')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response['Location'], 'https://www.google.com')

    def test_redirect_invalid_code(self):
        """Invalid short code returns 404."""
        response = self.client.get('/nonexistent123')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_redirect_increments_access_count(self):
        """Redirect increments the access counter."""
        mapping = URLMapping.objects.create(
            original_url="https://example.com"
        )
        self.assertEqual(mapping.access_count, 0)
        
        self.client.get(f'/{mapping.short_code}')
        
        mapping.refresh_from_db()
        self.assertEqual(mapping.access_count, 1)


class HealthCheckViewTests(APITestCase):
    """Tests for GET /health endpoint."""

    def test_health_check_returns_ok(self):
        """Health check returns ok status."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'ok')


class URLStatsViewTests(APITestCase):
    """Tests for GET /stats/{short_code} endpoint."""

    def test_stats_valid_code(self):
        """Stats endpoint returns URL statistics."""
        mapping = URLMapping.objects.create(
            original_url="https://example.com"
        )
        response = self.client.get(f'/stats/{mapping.short_code}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['short_code'], mapping.short_code)
        self.assertEqual(response.data['original_url'], 'https://example.com')
        self.assertIn('access_count', response.data)

    def test_stats_invalid_code(self):
        """Stats for invalid code returns 404."""
        response = self.client.get('/stats/nonexistent')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EdgeCaseTests(APITestCase):
    """Tests for edge cases and special scenarios."""

    def test_very_long_url(self):
        """Very long URLs are handled correctly."""
        long_path = 'a' * 1000
        long_url = f'https://example.com/{long_path}'
        response = self.client.post(
            '/shorten',
            {'url': long_url},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_url_with_special_characters(self):
        """URLs with special characters are handled."""
        special_url = 'https://example.com/path?query=value&foo=bar#section'
        response = self.client.post(
            '/shorten',
            {'url': special_url},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify redirect works
        short_code = response.data['short_code']
        redirect_response = self.client.get(f'/{short_code}')
        self.assertEqual(redirect_response['Location'], special_url)

    def test_unicode_in_url(self):
        """URLs with unicode characters are handled."""
        unicode_url = 'https://example.com/path/日本語'
        response = self.client.post(
            '/shorten',
            {'url': unicode_url},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_multiple_ips_independent_rate_limits(self):
        """Different IPs have independent rate limits."""
        RateLimitRecord.objects.all().delete()
        
        # Simulate request from IP 1
        with patch('shortener.rate_limiter.get_client_ip', return_value='10.0.0.1'):
            for i in range(5):
                response = self.client.post(
                    '/shorten',
                    {'url': f'https://example.com/ip1/{i}'},
                    format='json'
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Simulate request from IP 2 (should still be allowed)
        with patch('shortener.rate_limiter.get_client_ip', return_value='10.0.0.2'):
            response = self.client.post(
                '/shorten',
                {'url': 'https://example.com/ip2'},
                format='json'
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
