import logging

from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.db import DatabaseError, IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import URLMapping
from .serializers import ShortenURLRequestSerializer, ShortenURLResponseSerializer
from .rate_limiter import check_rate_limit, get_rate_limit_headers

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """Simple health check for monitoring."""
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({'status': 'ok'})


class ShortenURLView(APIView):
    """Create shortened URL. Rate limited to prevent abuse."""
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # check rate limit first
        rl_result = check_rate_limit(request)
        rl_headers = get_rate_limit_headers(rl_result)
        
        if not rl_result.allowed:
            resp = Response(
                {
                    'error': 'Rate limit exceeded',
                    'detail': 'Too many requests. Please try again later.',
                    'retry_after': rl_result.retry_after
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
            for k, v in rl_headers.items():
                resp[k] = v
            return resp
        
        serializer = ShortenURLRequestSerializer(data=request.data)
        if not serializer.is_valid():
            resp = Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            for k, v in rl_headers.items():
                resp[k] = v
            return resp
        
        # create the mapping
        try:
            url_mapping = URLMapping.objects.create(
                original_url=serializer.validated_data['url']
            )
        except IntegrityError:
            # rare collision, try once more
            logger.warning("Short code collision, retrying")
            try:
                url_mapping = URLMapping.objects.create(
                    original_url=serializer.validated_data['url']
                )
            except IntegrityError:
                logger.error("Failed to create URL after retry")
                return Response(
                    {'error': 'Could not generate short code. Try again.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        except DatabaseError as e:
            logger.error(f"DB error: {e}")
            return Response(
                {'error': 'Database error'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        out = ShortenURLResponseSerializer(url_mapping, context={'request': request})
        resp = Response(out.data, status=status.HTTP_201_CREATED)
        for k, v in rl_headers.items():
            resp[k] = v
        return resp


class RedirectView(APIView):
    """Redirect short code to original URL."""
    authentication_classes = []
    permission_classes = []

    def get(self, request, short_code):
        url_mapping = get_object_or_404(URLMapping, short_code=short_code)
        url_mapping.increment_access_count()
        return HttpResponseRedirect(url_mapping.original_url)


class URLStatsView(APIView):
    """Get stats for a shortened URL."""
    authentication_classes = []
    permission_classes = []

    def get(self, request, short_code):
        mapping = get_object_or_404(URLMapping, short_code=short_code)
        return Response({
            'short_code': mapping.short_code,
            'original_url': mapping.original_url,
            'created_at': mapping.created_at,
            'access_count': mapping.access_count
        })
