# Tinder-like Swipe Starter

This workspace contains a Next.js frontend and a Flask backend to demo a Tinder-like swipe UI for products.

Structure:
- `frontend/` - Next.js app (runs on :3000)
- `backend/` - Flask API (runs on :5000)

See the individual READMEs for run instructions.

Quick run (macOS):

1. Start backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

2. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and try swiping cards left/right. The frontend proxies API requests to `http://localhost:5000` by default.

Smoke test checklist:
- Backend responds at http://localhost:5000/recommendations
- Frontend loads and shows cards
- Swiping a card sends a POST to /api/swipe which proxies to backend

