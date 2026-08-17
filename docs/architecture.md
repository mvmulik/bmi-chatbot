# BMI Chatbot architecture overview

## Components

1. **Frontend (`frontend/`)** — React + TypeScript + Vite SPA that will host the chat UI.
2. **Backend (`backend/`)** — FastAPI service for health, chat, and retrieval endpoints.
3. **Crawler (`crawler/`)** — Playwright + BeautifulSoup pipeline (not implemented yet).
4. **Data (`data/`)** — Raw crawls, processed chunks, and ChromaDB persistence.
5. **AI** — Azure OpenAI or OpenAI-compatible providers configured via `.env`.

## Local ports

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
