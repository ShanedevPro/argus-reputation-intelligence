# Argus SaaS Frontend

This is the Argus analyst workbench frontend built on the Vercel Chatbot / AI SDK foundation.

## Local Development

Install dependencies from this directory:

```bash
pnpm install
```

Configure environment variables with `apps/argus-saas/.env.example` and the root `.env.example`. Do not commit `.env` files.

Run the frontend through the root local demo script when using the Flask backend:

```bash
ARGUS_FRONTEND_PORT=3010 ./scripts/run_argus_local_demo.sh
```

## Notes

- The frontend talks to the Flask backend for Argus crawl, search, report, and artifact workflows.
- The default public package does not include provider API keys or runtime database state.
- See the repository root `README.md` for full setup and sample reports.
