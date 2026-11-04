# SharpBuild AI Website Assistant: frontend

A Next.js demo page with a reusable chat widget (`src/components/ChatWidget.tsx`) that talks to the FastAPI backend in `../Backend`.

## Run it

1. Start the backend first (in `Backend`): `uvicorn app.main:app --reload`
2. In this folder:
   ```
   npm install
   copy .env.example .env.local
   npm run dev
   ```
3. Open **http://localhost:3000** (use `localhost`, not `127.0.0.1`: the backend only allows that origin by default).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Development server |
| `npm test` | Unit and component tests (Vitest) |
| `npm run typecheck` | TypeScript check |
| `npm run build` | Production build |

## Notes

- The widget keeps the conversation in memory only. Nothing is stored in the browser.
- Each question is answered on its own: the backend does not use earlier messages as context yet.
- Answers are rendered as plain text, and only http(s) source links are ever shown as links.
- `NEXT_PUBLIC_API_URL` is baked in at build time. Change it before `npm run build` when deploying.
