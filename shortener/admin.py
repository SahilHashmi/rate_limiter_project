from django.contrib import admin
from .models import URLMapping, RateLimitRecord


@admin.register(URLMapping)
class URLMappingAdmin(admin.ModelAdmin):
    list_display = ['short_code', 'original_url', 'created_at', 'access_count']
    search_fields = ['short_code', 'original_url']
    readonly_fields = ['short_code', 'created_at', 'access_count']


@admin.register(RateLimitRecord)
class RateLimitRecordAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'request_count', 'window_start']
    search_fields = ['ip_address']
