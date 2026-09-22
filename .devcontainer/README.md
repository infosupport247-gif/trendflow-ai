# TrendFlow AI in GitHub Codespaces

This project is configured so the full Docker Compose stack can start automatically inside GitHub Codespaces.

## Start without local Terminal

1. Open the TrendFlow repository on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on main**.
3. Wait for the environment to finish creating.
4. Docker Compose starts automatically.
5. Open the forwarded **8080** port.

The application entrypoint is the Caddy web service on port 8080.

## Important

Codespaces is a development/cloud workspace, not permanent production hosting. The full production deployment still requires persistent hosting for PostgreSQL, Redis, object storage, API, worker, scheduler and HTTPS.
