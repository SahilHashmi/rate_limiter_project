# Technical Documentation

This doc covers the internals of the URL shortener - mainly how the rate limiter works and what I'd change for higher scale.

**Live Demo:** http://31.97.206.77:9000/

## Contents

1. [How it's built](#architecture)
2. [Rate limiting approach](#rate-limiting)
3. [Handling concurrency](#concurrency)
4. [Scaling to 10k RPS](#scaling-considerations)
5. [Database design](#database)
6. [API endpoints](#api)
7. [Time breakdown](#time-spent)

---

## Architecture

Pretty simple flow:

```
Request → Rate Limit Check → URL Logic → Database
```

For POST /shorten:
1. Check if IP is rate limited
2. If yes → return 429
3. If no → validate URL, generate short code, save to DB

For GET /{code}:
1. Look up short code in DB
2. Increment access count
3. Return 302 redirect

### Tech used

- **Django 4.2** - handles routing, ORM, etc
- **DRF** - makes the JSON API stuff easier
- **SQLite** - stores URLs and rate limit counters
- **Gunicorn** - production WSGI server

---

## Rate Limiting

I implemented a **fixed window counter** - basically the simplest rate limiting approach that actually works.

### How it works

```
Window 1 (0-60s):    [1] [2] [3] [4] [5] [BLOCKED]
Window 2 (60-120s):  [1] [2] [3] ...
```

- Divide time into 60-second windows
- Count requests per IP in each window
- Block when count hits 5
- Reset count when new window starts

### Why this approach?

I considered a few options:

| Algorithm | Why I didn't use it |
|-----------|--------------------|
| Token Bucket | More complex than needed for this |
| Sliding Window | Higher memory usage, stores timestamps |
| Leaky Bucket | Adds latency by queuing requests |

Fixed window has a known edge case (burst at window boundaries) but for 5 req/min it's not a real problem.

### The code

The actual check happens in `RateLimitRecord.check_and_increment()`. It:
1. Gets or creates a record for the IP
2. Checks if the window expired (resets if so)
3. Increments counter atomically
4. Returns whether the request is allowed

---

## Concurrency

The tricky part with rate limiting is the race condition:

```
Thread A: reads count = 4
Thread B: reads count = 4
Thread A: 4 < 5, increments to 5 ✓
Thread B: 4 < 5, increments to 5 ✓  ← should've been blocked!
```

I handle this using Django's `F()` expression which translates to an atomic SQL update:

```python
record.request_count = models.F('request_count') + 1
```

This becomes `SET request_count = request_count + 1` in SQL - the database handles the atomicity.

**SQLite caveat:** It uses file-level locking, so writes are serialized. Fine for this demo, but would need Redis for real scale.

---

## Scaling Considerations

If this needed to handle 10,000 requests/second, here's what would break and how I'd fix it:

### Problem 1: Database writes (Critical)

Every rate limit check writes to the DB. SQLite tops out around 100-500 writes/sec.

**Fix:** Use Redis with `INCR` - it handles 100k+ ops/sec easily.

### Problem 2: Single server

**Fix:** Multiple app servers behind a load balancer, with Redis as the shared rate limit store.

### Problem 3: URL lookups

**Fix:** Cache popular short codes in Redis/Memcached.

### What the architecture would look like

```
Load Balancer
     |
  [App 1] [App 2] [App 3]
     |       |       |
     +-------+-------+
             |
    Redis (rate limits) + PostgreSQL (URLs)
```

---

## Database

Two tables:

**URLMapping** - stores the short code → URL mappings
- `short_code` (indexed, unique)
- `original_url`
- `access_count`
- `created_at`

**RateLimitRecord** - tracks request counts per IP
- `ip_address` (indexed, unique)
- `window_start`
- `request_count`

---

## API

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/shorten` | POST | Create short URL (rate limited) |
| `/{code}` | GET | Redirect to original |
| `/health` | GET | Health check |
| `/stats/{code}` | GET | View access count |

See README for request/response examples.

---

## Time Spent

| Task | Time |
|------|------|
| Initial setup, Django config | 45 min |
| URL shortener logic | 1 hour |
| Rate limiter implementation | 1.5 hours |
| Testing and fixing bugs | 1.5 hours |
| Writing tests | 45 min |
| Documentation | 1 hour |
| Deployment config, cleanup | 30 min |
| **Total** | **~7 hours** |

Spent more time than expected on the rate limiter - had to think through the concurrency edge cases and test them properly.
