# BMI Chatbot

Scaffold for a RAG chatbot with a React frontend, FastAPI backend, Playwright crawler, and ChromaDB vector store.

## Architecture

| Layer | Stack |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI |
| Crawler | Python, Playwright, BeautifulSoup *(not implemented yet)* |
| Vector DB | ChromaDB *(wired via config; indexing not implemented yet)* |
| AI | Azure OpenAI / OpenAI-compatible APIs via environment variables |

## Project layout

```
bmi-chatbot/
  frontend/          # React + TypeScript + Vite UI
  backend/           # FastAPI application
  crawler/           # Web crawler package (placeholder)
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
- (Later) Playwright browsers for the crawler

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

## Status

This repository currently provides a runnable frontend and backend shell only. The crawler and chatbot RAG flow are intentionally not implemented yet.
