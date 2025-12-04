import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.db import DatabaseError

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Wrap DRF exceptions in consistent format."""
    response = exception_handler(exc, context)

    if response is not None:
        return response

    # handle DB errors
    if isinstance(exc, DatabaseError):
        logger.error(f"DB error: {exc}")
        return Response(
            {'error': 'Database unavailable'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # catch-all
    logger.exception(f"Unhandled: {exc}")
    return Response(
        {'error': 'Internal server error'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
