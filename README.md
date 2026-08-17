# BMI Chatbot — Local Windows Runbook

Project root:

```powershell
cd "C:\Users\mvmulik\OneDrive - Burns & McDonnell\Documents\Manali Mulik\Project\bmi-chatbot"
```

## One-time setup

```powershell
cd "C:\Users\mvmulik\OneDrive - Burns & McDonnell\Documents\Manali Mulik\Project\bmi-chatbot"

# Root environment (Azure OpenAI / OpenAI-compatible + Chroma settings)
Copy-Item .env.example .env
notepad .env

# Frontend API base URL (no secrets)
Copy-Item frontend\.env.example frontend\.env

# Python venv + dependencies (scripts also install as needed)
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pip install -r crawler\requirements.txt
pip install -r processor\requirements.txt
playwright install chromium

# Frontend dependencies
cd frontend
npm install
cd ..
```

Required `.env` values for chat + indexing:

- `OPENAI_API_TYPE=azure` (or `openai`)
- `OPENAI_API_KEY=...`
- `OPENAI_API_BASE=...` (Azure endpoint)
- `OPENAI_API_VERSION=...`
- `OPENAI_DEPLOYMENT_NAME=...` (chat model deployment)
- `OPENAI_EMBEDDING_DEPLOYMENT_NAME=...`
- `CHROMA_PERSIST_DIRECTORY=./data/chroma`
- `CHROMA_COLLECTION_NAME=bmi_documents`

## Daily workflow (PowerShell scripts)

Open separate terminals from the project root.

### 1. Start backend

```powershell
cd "C:\Users\mvmulik\OneDrive - Burns & McDonnell\Documents\Manali Mulik\Project\bmi-chatbot"
.\scripts\start-backend.ps1
```

First-time dependency install:

```powershell
.\scripts\start-backend.ps1 -InstallDeps
```

- API: http://localhost:8000  
- Health: http://localhost:8000/health  
- Docs: http://localhost:8000/docs  

### 2. Start frontend

```powershell
cd "C:\Users\mvmulik\OneDrive - Burns & McDonnell\Documents\Manali Mulik\Project\bmi-chatbot"
.\scripts\start-frontend.ps1
```

- UI: http://localhost:5173  
- Uses `frontend/.env` → `VITE_API_BASE_URL=http://localhost:8000`

### 3. Crawl BMI Hub

```powershell
cd "C:\Users\mvmulik\OneDrive - Burns & McDonnell\Documents\Manali Mulik\Project\bmi-chatbot"
.\scripts\crawl.ps1 -MaxPages 50
```

First run opens a browser for manual SSO login. Press Enter in the terminal after you are signed in.  
Re-authenticate later with:

```powershell
.\scripts\crawl.ps1 -Reauth -MaxPages 50
```

Output: `data\raw\crawl_<timestamp>\`

### 4. Process content

```powershell
.\scripts\process.ps1
```

Output: `data\processed\process_<timestamp>\`

### 5. Build / update vector index

```powershell
# First time or after major content changes
.\scripts\index.ps1 -Mode full

# Later updates (skips existing chunk IDs)
.\scripts\index.ps1 -Mode incremental

# Inspect collection
.\scripts\index.ps1 -Mode stats
```

### 6. Run tests

```powershell
.\scripts\test.ps1
```

### 7. Verify integration (backend + frontend + real chat/sources)

With backend and frontend already running, and after crawl → process → index:

```powershell
.\scripts\verify-integration.ps1
```

Optional custom question:

```powershell
.\scripts\verify-integration.ps1 -Question "Where do I find safety guidance on BMI Hub?"
```

## Manual smoke checks

```powershell
# Health
Invoke-RestMethod http://127.0.0.1:8000/health

# Chat (requires indexed Chroma content + valid LLM credentials)
$body = @{
  message = "What information is available on BMI Hub?"
  conversationId = "local-1"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/chat `
  -ContentType "application/json" `
  -Body $body
```

## Script reference

| Script | Purpose |
| --- | --- |
| `scripts\start-backend.ps1` | Start FastAPI on port 8000 |
| `scripts\start-frontend.ps1` | Start Vite UI on port 5173 |
| `scripts\crawl.ps1` | Authenticated BMI Hub crawl |
| `scripts\process.ps1` | Clean + chunk raw crawl output |
| `scripts\index.ps1` | full / incremental / stats / clear Chroma index |
| `scripts\test.ps1` | pytest + frontend build |
| `scripts\verify-integration.ps1` | Live health/UI/chat+sources checks |

## Deployment (LOCAL / DEV / TEST / PROD)

See **[docs/deployment.md](docs/deployment.md)** for environment separation, Docker builds, CORS, auth session handling, vector DB population, smoke tests, BMI Hub URL verification, and rollback.

Quick local Docker:

```powershell
Copy-Item .env.local.example .env.local
# fill secrets in .env.local
docker compose up --build
```

Environment templates (no secrets):

- `.env.example`
- `.env.local.example`
- `.env.dev.example`
- `.env.test.example`

Verified locally without fake fixtures:

- Backend starts (`.\scripts\start-backend.ps1`)
- Frontend starts (`.\scripts\start-frontend.ps1`)
- `GET /health` and `GET /api/health` return healthy
- Frontend loads BMI Hub Assistant UI and can reach the backend API base URL
- `.\scripts\test.ps1` — 22 pytest tests + frontend build passed

Not yet verifiable until you complete the data pipeline on this machine:

- Project root `.env` is missing (Azure OpenAI credentials required for embeddings/chat)
- `data/raw` and `data/processed` are empty (no BMI Hub crawl yet)
- Chroma collection `bmi_documents` count is `0`

After you configure `.env` and run crawl → process → index, finish with:

```powershell
.\scripts\verify-integration.ps1
```

That script asserts a real chat answer with non-empty source titles/URLs.

- Execution policy (if scripts are blocked):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- Do not put API keys in the React app. Only `VITE_API_BASE_URL` belongs in `frontend/.env`.
- Chat answers are grounded in indexed BMI Hub content only.
