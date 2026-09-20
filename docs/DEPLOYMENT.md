# TrendFlow AI v6.1 Deployment

1. Copy the v6.1 release files into this repository.
2. Configure production secrets outside Git.
3. Point DNS for your application domain to the VPS.
4. Run the supplied production deployment script.
5. Verify /health/live and /health/ready.
6. Open the HTTPS application URL.

The application uses Caddy for HTTPS and same-origin routing, FastAPI for the API, PostgreSQL for persistence, Redis for jobs, MinIO/S3 for assets, workers for background processing, and a scheduler for autonomous cycles.

Never commit .env or provider credentials.
