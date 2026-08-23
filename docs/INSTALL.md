# Installation & deployment

## Requirements

- Python 3.12+
- (Production) PostgreSQL 14+ and, optionally, Redis 6+
- (Optional) Docker & Docker Compose

## Local development

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env
python -m app generate-key           # -> UPGI_SECRET_ENCRYPTION_KEY
# set a strong UPGI_JWT_SECRET_KEY too

python -m app serve --reload
```

The default database is SQLite and the schema is auto-created outside production.

## Configuration

All settings come from environment variables prefixed `UPGI_` (or `.env`).
See [`.env.example`](../.env.example) for the full list. Key ones:

| Variable | Purpose |
|----------|---------|
| `UPGI_ENVIRONMENT` | `local` / `testing` / `staging` / `production` |
| `UPGI_DATABASE_URL` | async SQLAlchemy URL (`postgresql+asyncpg://…`) |
| `UPGI_JWT_SECRET_KEY` | 32+ char signing secret |
| `UPGI_SECRET_ENCRYPTION_KEY` | base64url 32-byte AES key |
| `UPGI_RATE_LIMIT_*` | request quota |
| `UPGI_CORS_ALLOW_ORIGINS` | JSON array of allowed origins |

In `production` the app refuses to start with insecure defaults.

## Database migrations

```bash
alembic upgrade head                 # apply
alembic revision --autogenerate -m "add table"   # create a new migration
```

The migration environment reads the URL and models from the app, so migrations
always match the ORM.

## Docker

```bash
# Single image
docker build -t upgi:latest .
docker run -p 8000:8000 --env-file .env upgi:latest

# Full stack: API + PostgreSQL + Redis + NGINX
docker compose up --build -d
# API via NGINX: http://localhost:8080
```

The image runs as a non-root user and ships a container `HEALTHCHECK` hitting
`/health/live`.

## Production notes

- Terminate TLS at NGINX or your load balancer; the app emits HSTS.
- Run multiple workers/replicas behind the proxy; use the Redis-backed rate
  limiter for a shared quota across replicas.
- Provide secrets via your platform's secret manager, never in the image.
- Scrape `/metrics` with Prometheus; the repo's compose file can be extended
  with Prometheus + Grafana.
- Scale horizontally: the app is stateless; state lives in PostgreSQL/Redis.

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `RuntimeError: Insecure production configuration` | Set real `UPGI_JWT_SECRET_KEY` / `UPGI_SECRET_ENCRYPTION_KEY`, disable debug |
| `provider ... is not configured` | Add a `ProviderConfig` for that owner, or use the `mock` provider |
| `signature_invalid` / `replay_detected` on webhooks | Wrong signing secret or clock skew beyond the replay window |
| 429 responses | Rate limit hit; raise `UPGI_RATE_LIMIT_REQUESTS` or back off |
