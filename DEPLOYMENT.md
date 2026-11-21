# Deploying the SharpBuild AI Website Assistant

## 1. Environment variables

**Backend** (Vercel project settings, never committed)

| Variable | Production value |
|---|---|
| `DATABASE_URL` | pooled Postgres URL ending in `?sslmode=require` |
| `GEMINI_API_KEY` | your key |
| `ALLOWED_ORIGINS` | `https://www.sharpbuild.io` (comma-separated, https only) |
| `ALLOWED_ORIGIN_REGEX` | only for preview URLs, e.g. `https://sharpbuild-[a-z0-9-]+\.vercel\.app` |
| `TRUST_FORWARDED_FOR` | `true` on Vercel (otherwise all visitors share one rate-limit bucket) |
| `RATE_LIMIT_BACKEND` | `database` |
| `ENABLE_DOCS` | `false` |
| `LOG_FORMAT` | `json` |
| `ADMIN_TOKEN` and `CRON_SECRET` | the **same** random value, 32+ characters |
| `LEAD_WEBHOOK_URL`, `LEAD_WEBHOOK_SECRET` | your CRM hook (https) and a signing secret |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `LEAD_EMAIL_FROM`, `LEAD_EMAIL_TO` | optional email alert |

Generate a token: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

**Frontend**: `NEXT_PUBLIC_API_URL=https://<your backend>`, set for Production (and Preview if you use it).
It is baked in at build time; a Production build fails if it is missing, not https, or localhost.

## 2. Release order

1. `pytest -q` and `npm test` are green. Run `python -m scripts.eval_answers` for a release that touches prompts, retrieval or models.
2. Load the production env vars, then `python -m scripts.preflight --production` must print `0 error(s)`.
3. Database first: run any new `migrate_*.sql`, then `python -m scripts.init_db` (adds missing tables only). Migrations are additive, so the previous release keeps working on the new schema.
4. Deploy the backend.
5. `python -m scripts.smoke_test https://<backend> --origin https://www.sharpbuild.io --chat --token "$ADMIN_TOKEN"` must end `N/N checks passed`.
6. Deploy the frontend. Open the live site and ask one question; check the browser console for CORS errors.

## 3. Retry job for lead notifications (Vercel Cron)

Add to the backend's `vercel.json` (merge with what is there):

```json
{ "crons": [ { "path": "/internal/retry-lead-notifications", "schedule": "*/15 * * * *" } ] }
```

Vercel Cron calls with `Authorization: Bearer <CRON_SECRET>`, which is why `CRON_SECRET` must equal `ADMIN_TOKEN`.
Check your Vercel plan's cron frequency limit; on a plan that only allows daily runs, call the URL from an external scheduler instead.

## 4. Rollback

- Code: Vercel > Deployments > previous deployment > Promote / Instant Rollback (backend and frontend separately).
- Database: nothing to undo; keep every migration additive (new columns and tables only).
- If answers suddenly fail: check `LOG_FORMAT=json` logs for `model ... failed` lines, then `python -m scripts.try_models`.

## 5. Routine

- Weekly: `python -m scripts.log_report <exported logs>` (no-answer rate, errors, latency); `GET /internal/stats` should show `gave_up: 0`.
- Uptime monitor on `GET /health` (it checks the database).
- Rotate `GEMINI_API_KEY`, `ADMIN_TOKEN` and `LEAD_WEBHOOK_SECRET` if anyone who had them leaves.
