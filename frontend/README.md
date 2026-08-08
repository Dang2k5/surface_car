# Visual QC Agent frontend

Bilingual (English/Vietnamese) Next.js/React dashboard for the Visual QC mock demo.

## Prerequisites

- Node.js 22.13 or newer
- The FastAPI backend running at `http://127.0.0.1:8000`

## Local setup

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Open the URL printed in the terminal. The dashboard defaults to `http://127.0.0.1:8000`; change `NEXT_PUBLIC_API_BASE_URL` in `.env.local` only when the backend uses another address or port.

## Demo behavior

Select **Agent inspection**, choose one of eight concrete image examples, and press
**Start inspection**. Each image already carries the mock CV behavior needed to
exercise a graph route. The dashboard shows:

- YOLO-style defect evidence for scratches, dents and paint defects
- streamed execution of every LangGraph node
- confidence-based routing and verification loops
- real HITL checkpoint/resume controls
- one shared trace for live inspection, QC queue and history
- a confirmed history cleanup action that never deletes source images
- concrete deterministic repair/reinspection methods

## Validate a production-style build

```powershell
npm run build
```

The UI uses mock data and placeholder technical limits. It is not production approval for vehicle release.
