# TrendFlow AI v6.1 deployment

## Local
Run the stack with Docker Desktop:
docker compose up --build
Then open http://localhost:8080.

Never open frontend/index.html directly. Caddy serves the UI and proxies /api, /health and /metrics to FastAPI.

## Production
1. Copy the repository to an Ubuntu VPS.
2. Create .env from .env.production.example using strong random secrets.
3. Point the domain A/AAAA record to the VPS.
4. Run ops/deploy.sh your.domain.com.
5. Verify https://your.domain.com/health/live and /health/ready.
6. Add provider credentials only through the server environment or a secret manager.

Do not commit .env, OAuth client secrets, API keys, JWT secrets, database passwords, or token-vault keys.

## GitHub
The repository is private and CI validates Python syntax and Compose configuration on pushes and pull requests.
