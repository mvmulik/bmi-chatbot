# BMI Chatbot

Scaffold for a RAG chatbot with a React frontend, FastAPI backend, Playwright crawler, and ChromaDB vector store.

## Architecture

| Layer | Stack |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI |
| Crawler | Python, Playwright, BeautifulSoup (interactive auth + BMI Hub crawl) |
| Processor | HTML cleaning + token chunking for RAG (no embeddings yet) |
| Vector DB | ChromaDB indexing from processed chunks (Azure/OpenAI embeddings via env) |
| AI | Azure OpenAI / OpenAI-compatible APIs via environment variables |

## Project layout

```
bmi-chatbot/
  frontend/          # React + TypeScript + Vite UI
  backend/           # FastAPI application
  crawler/           # BMI Hub Playwright crawler
  processor/         # Clean + chunk pipeline (data/raw → data/processed)
  data/raw/          # Raw crawled content
  data/processed/    # Cleaned / chunked documents
  data/chroma/       # ChromaDB persistence
  scripts/           # Utility scripts
  tests/             # Shared / integration tests
  docs/              # Project documentation
```

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- Playwright Chromium (`playwright install chromium`)

## Setup

### 1. Environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` with your Azure OpenAI (or OpenAI-compatible) credentials when you are ready to wire AI features.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs  
Health check: http://localhost:8000/health

### 3. Frontend

```powershell
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

> Note: `npm run dev` uses Node to launch Vite directly so Windows paths containing `&` (for example OneDrive company folders) work reliably.

### 4. Crawler (BMI Hub)

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r crawler\requirements.txt
playwright install chromium
python -m crawler --max-pages 50
```

First run opens a headed browser for manual login. The session is saved to `data/auth/playwright_storage_state.json` (gitignored) and reused on later crawls. Use `--reauth` to log in again.

Raw pages and `crawl_report.json` are written under `data/raw/crawl_<timestamp>/`.

### 5. Content processor

```powershell
pip install -r processor\requirements.txt
python -m processor
```

Processes the newest `data/raw/crawl_*` run into `data/processed/process_<timestamp>/` with cleaned documents, `chunks.jsonl`, and `process_report.json`. Default chunk size is 1000 tokens with 150-token overlap.

```powershell
python -m processor --crawl-dir data\raw\crawl_YYYYMMDDTHHMMSSZ --chunk-size 1000 --chunk-overlap 150
```

### 6. Vector indexing (ChromaDB)

Requires embedding credentials in `.env` (Azure OpenAI recommended for Dev/Test):

```powershell
pip install -r crawler\requirements.txt
python -m crawler.indexer full
python -m crawler.indexer incremental
python -m crawler.indexer stats
python -m crawler.indexer clear
```

- `full` — delete collection and rebuild from the newest `data/processed/process_*` run  
- `incremental` — upsert only chunk IDs not already present  
- `stats` — collection count and sample IDs  
- `clear` — delete the collection  

Optional: `python -m crawler.indexer full --process-dir data\processed\process_YYYYMMDDTHHMMSSZ`

## Status

Frontend, backend, crawler, content processor, and Chroma indexing are runnable locally. Chat API / RAG query endpoints are not implemented yet.
