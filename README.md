# SharpBuild AI Website Assistant

An AI-powered support assistant for [SharpBuild](https://sharpbuild.io/). The
chatbot answers questions using the site's published content, streams responses,
links to sources, and offers a human contact path when it cannot answer.

## Features

- Website knowledge-base question answering with grounded source links
- Streaming responses, suggested questions, and conversation controls
- Clear fallbacks and contact options when information is unavailable
- FastAPI backend with Gemini and PostgreSQL/pgvector
- Responsive Next.js chat widget and demo landing page

## Project layout

```text
Backend/    FastAPI API, retrieval and AI services, ingestion tools, tests
frontend/   Next.js app, chat widget, and frontend tests
```

## Local development

### Requirements

- Python version specified in `Backend/.python-version`
- Node.js and npm
- PostgreSQL with the pgvector extension available
- A Google Gemini API key

### 1. Configure and run the backend

In PowerShell:

```powershell
cd Backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `Backend/.env` and set `DATABASE_URL` to your PostgreSQL connection string
and `GEMINI_API_KEY` to your key. The database must support pgvector. Initialize
the database schema and start the API:

```powershell
python -m scripts.init_db
uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`. Its health endpoint is
`http://127.0.0.1:8000/health`.

### 2. Configure and run the frontend

In a second PowerShell window:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The default frontend API
URL is `http://127.0.0.1:8000`; the backend's default CORS origin allows
`http://localhost:3000`.

## Environment variables

### Backend (`Backend/.env`)

| Variable | Required | Description |
|---|---:|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string with pgvector support |
| `GEMINI_API_KEY` | For AI answers | Google AI Studio API key |
| `ALLOWED_ORIGINS` | No | Comma-separated or JSON list of allowed browser origins |
| `ALLOWED_ORIGIN_REGEX` | No | Optional origin pattern, useful for preview deployments |
| `TRUST_FORWARDED_FOR` | No | Enable only behind a trusted proxy that overwrites this header |

Model and rate-limit settings have defaults in `Backend/app/core/config.py`.
Never commit `.env` files, API keys, or database credentials.

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---:|---|
| `NEXT_PUBLIC_API_URL` | No | Base URL of the FastAPI service; defaults to `http://127.0.0.1:8000` |

`NEXT_PUBLIC_API_URL` is included in the frontend bundle at build time. Set the
production API URL in the frontend deployment environment before building.

## Tests and checks

Run backend tests from `Backend/`:

```powershell
pytest
```

Run frontend checks from `frontend/`:

```powershell
npm test
npm run typecheck
npm run build
```

## Deployment

The backend has a Vercel entry point at `Backend/index.py`; the frontend is a
separate Next.js app in `frontend/`. Configure each Vercel project to use its
respective directory as its project root.

Set the backend's `DATABASE_URL`, `GEMINI_API_KEY`, and `ALLOWED_ORIGINS` in its
Vercel environment. `ALLOWED_ORIGINS` must include the deployed frontend origin.
Set `NEXT_PUBLIC_API_URL` in the frontend project's environment to the deployed
backend URL, then redeploy the frontend so the URL is included in its build.
For Vercel deployments, enable `TRUST_FORWARDED_FOR` only when requests pass
through Vercel's trusted proxy.

## Privacy

Questions are sent to the backend and processed by Google's Gemini API. Do not
send personal or sensitive information through the demo chatbot.
