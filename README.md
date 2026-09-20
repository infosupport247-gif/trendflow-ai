# TrendFlow AI — Influencer Operating System

TrendFlow AI is an autonomous AI Influencer Operating System.

## v6.1 deployment release

The deployment release includes:
- Influencer DNA and persistent identity
- AI content generation
- Autonomous intelligence loop
- Content approval and publishing authorization gates
- Social publishing adapters
- Analytics and learning architecture
- PostgreSQL + Redis + MinIO
- Alembic migrations
- Caddy same-origin frontend/API routing
- Production deployment scripts
- Automated PostgreSQL backups
- Prometheus/Grafana monitoring
- macOS/Windows desktop scaffold

## Local web URL

The intended local web entrypoint is:

http://localhost:8080

Do not open frontend/index.html directly. The v6.1 Caddy web service serves the frontend and proxies /api/* to FastAPI.

## Deployment

See docs/DEPLOYMENT.md in the v6.1 release package.

> Secrets and OAuth credentials must never be committed to this repository.
