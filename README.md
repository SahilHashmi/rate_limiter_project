# URL Shortener with Rate Limiting

A simple URL shortener API with a custom-built rate limiter. Built this as a take-home assignment to demonstrate handling rate limiting without relying on third-party packages.

**Live Demo:** http://31.97.206.77:9000/

## What it does

- Shorten long URLs into short codes
- Redirect short codes back to original URLs
- Rate limit the shorten endpoint (5 requests per minute per IP)
- Return proper 429 responses with Retry-After headers

## Built with

- Python 3.10+
- Django 4.2 + DRF
- SQLite (easy to swap for Postgres)
- Gunicorn for production

## Getting Started

```bash
# setup
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate # Mac/Linux
pip install -r requirements.txt

# run migrations
python manage.py migrate

# start server
python manage.py runserver
```

API runs at `http://127.0.0.1:8000`

## API

### POST /shorten
Create a short URL.

```bash
curl -X POST http://127.0.0.1:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some/long/path"}'
```

Returns:
```json
{
  "short_code": "Ab3x9Q",
  "short_url": "http://127.0.0.1:8000/Ab3x9Q",
  "original_url": "https://example.com/some/long/path"
}
```

If you hit the rate limit (6th request within a minute):
```json
{"error": "Rate limit exceeded", "retry_after": 45}
```

### GET /{short_code}
Redirects to the original URL (302).

### GET /health
Returns `{"status": "ok"}` - useful for monitoring.

### GET /stats/{short_code}
Shows how many times a link was accessed.

## Rate Limiting

The `/shorten` endpoint is rate limited to 5 requests per IP per minute. I went with a fixed window counter approach - it's simple and works well for this use case.

Every response includes these headers:
- `X-RateLimit-Limit` - max requests allowed
- `X-RateLimit-Remaining` - how many you have left
- `X-RateLimit-Reset` - window duration
- `Retry-After` - seconds to wait (only on 429)

You can tweak the limits via environment variables:
```bash
RATE_LIMIT_REQUESTS=5
RATE_LIMIT_WINDOW_SECONDS=60
```
 
## Testing with Postman

There is a ready-made Postman collection in the repo: `postman_collection.json`.

To use it:
- Open Postman → **Import**
- Select `postman_collection.json`
- Run the requests in order (health check → shorten → redirect → stats → rate limit test)

This makes it easy to quickly verify all endpoints and the rate limiter behaviour.

## Deploying

The app is a standard Django project and can be deployed on any platform that supports Python + Gunicorn (Heroku-style PaaS, a VPS, Docker, etc.).

Basic idea:
- Install dependencies with `pip install -r requirements.txt`
- Run `python manage.py migrate`
- Start with something like: `gunicorn rate_limiter_service.wsgi:application`

For production, remember to:
- Use a real secret key (`DJANGO_SECRET_KEY`)
- Set `DEBUG=False`
- Configure `ALLOWED_HOSTS`
- Use a proper database (e.g. PostgreSQL) and HTTPS

## Testing Rate Limits

Easiest way to test - just hit the endpoint 6 times quickly:

```bash
for i in {1..6}; do
  curl -X POST http://127.0.0.1:8000/shorten \
    -H "Content-Type: application/json" \
    -d '{"url": "https://example.com"}'
  echo ""
done
```

First 5 work, 6th gets a 429.

## Project Structure

```
├── manage.py
├── requirements.txt
├── rate_limiter_service/    # Django project config
│   └── settings.py, urls.py, wsgi.py
└── shortener/               # Main app
    ├── models.py            # URLMapping + RateLimitRecord
    ├── views.py             # API endpoints
    ├── rate_limiter.py      # The custom rate limiting logic
    └── serializers.py
```

See `DOCUMENTATION.md` for the technical deep-dive on how the rate limiter works and scaling considerations.
