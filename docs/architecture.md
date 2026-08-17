# BMI Chatbot architecture overview

## Components

1. **Frontend (`frontend/`)** — React BMI Hub Assistant chat UI with sources, loading, and error handling.
2. **Backend (`backend/`)** — FastAPI RAG API (`POST /api/chat`) with Chroma retrieval and grounded LLM answers.
3. **Crawler (`crawler/`)** — Playwright + BeautifulSoup crawler with interactive SSO login and host allow-list from env.
4. **Processor (`processor/`)** — Cleans HTML, preserves structure, and creates overlapping token chunks for RAG.
5. **Indexer (`crawler/indexer.py`)** — Embeds processed chunks and stores vectors/metadata in ChromaDB.
6. **Data (`data/`)** — Raw crawls, processed chunks, ChromaDB persistence, and gitignored auth storage.
7. **AI** — Azure OpenAI or OpenAI-compatible providers configured via environment variables.
8. **Deployment** — See `docs/deployment.md` for LOCAL / DEV / TEST / PROD. Docker assets live in `backend/Dockerfile`, `frontend/Dockerfile`, and `docker-compose.yml`.

## Local ports

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
