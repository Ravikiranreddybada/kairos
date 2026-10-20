# Kairos web: copilot

React + Vite + TypeScript + Tailwind v4. The first surface is the copilot chat, designed as a three-part requisition pad:
the white copy holds the answer, the canary copy holds the evidence (re-read from the same read-only REST endpoints the
tools use), and the pink copy holds the audit trail (grounding, tokens, cost, trace id, champion run).

## Run

```bash
# 1. API (from the repo root)
.venv/bin/kairos serve            # or: .venv/bin/uvicorn kairos.api.main:app --port 8000

# 2. Web
cd web
npm install
npm run dev                       # http://localhost:5188
```

The dev proxy forwards `/v1` to the API and adds the `X-API-Key` header, so the browser never holds a key.

| Env var | Default | Use |
|---|---|---|
| `KAIROS_API_URL` | `http://localhost:8000` | Where the API runs |
| `KAIROS_WEB_API_KEY` | `dev-key` | Key the proxy sends (must be in `KAIROS_API_KEYS`) |

`npm run build` type-checks and writes `dist/`. Serving `dist/` in production needs a reverse proxy that adds the key
the same way; do not put a key in the client bundle.
