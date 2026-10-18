# Runbook OS — 3D Operations UI

React + Vite frontend for the Runbook Following Agent. Includes an animated Three.js operations core, responsive dashboard, runbook upload, activity/log views, report summary, and API connection status.

## Local development

Requirements: Node.js 18+ and the Runbook Following Agent FastAPI backend.

```bash
cd frontend
npm install
npm run dev
```

Vite proxies supported backend paths to `http://127.0.0.1:8000`. Start the FastAPI backend separately. Open the local URL printed by Vite.

## Production build

```bash
npm run build
npm run preview
```

## Vercel deployment

Set the Vercel project Root Directory to `frontend`, Framework Preset to Vite, Build Command to `npm run build`, and Output Directory to `dist`.

The UI defaults to `https://runbook-following-agent2.onrender.com` for production API calls. Set `VITE_API_BASE_URL` in Vercel environment variables if the API URL changes. The backend must permit the deployed frontend origin through its CORS configuration.

## Backend integration notes

The UI reads `/openapi.json`, `/logs`, `/report`, and `/report/pdf`, and uploads Markdown files to `/upload`. Response rendering is defensive because log/report schemas may vary. The existing backend's `/parse`, `/execute`, approval, pause/resume, and retry endpoints are intentionally not triggered automatically by the redesign; their exact request schemas should be confirmed from the live OpenAPI document before wiring execution controls.

No fake execution success, synthetic metrics, or automatic command execution is shown. Keep server-side allowlists, command validation, and risky-command approval enabled.
