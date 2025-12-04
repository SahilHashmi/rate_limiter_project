import re
from urllib.parse import urlparse
from rest_framework import serializers
from .models import URLMapping


class ShortenURLRequestSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)

    def validate_url(self, value):
        parsed = urlparse(value)
        
        if parsed.scheme not in ('http', 'https'):
            raise serializers.ValidationError("Only http/https URLs allowed.")
        
        if not parsed.netloc:
            raise serializers.ValidationError("Invalid URL.")
        
        # block localhost
        host = parsed.netloc.split(':')[0]
        if host in ('localhost', '127.0.0.1', '0.0.0.0'):
            raise serializers.ValidationError("Localhost URLs not allowed.")
        
        # block private IPs
        if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', host):
            parts = [int(x) for x in host.split('.')]
            if parts[0] == 10:
                raise serializers.ValidationError("Private IPs not allowed.")
            if parts[0] == 172 and 16 <= parts[1] <= 31:
                raise serializers.ValidationError("Private IPs not allowed.")
            if parts[0] == 192 and parts[1] == 168:
                raise serializers.ValidationError("Private IPs not allowed.")
        
        return value


class ShortenURLResponseSerializer(serializers.ModelSerializer):
    short_url = serializers.SerializerMethodField()

    class Meta:
        model = URLMapping
        fields = ['short_code', 'short_url', 'original_url', 'created_at']

    def get_short_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/{obj.short_code}')
        return f'/{obj.short_code}'
