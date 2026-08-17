# Deployment Guide — BMI Chatbot

This guide separates **LOCAL**, **DEV**, **TEST**, and **PROD**.  
It does **not** assume a specific Burns & McDonnell hosting platform. Use whichever runtime your team provides (VM, Kubernetes, App Service, ECS, etc.).

All environment-specific behavior must come from **environment variables** / secret stores.  
Never commit secrets.

---

## Environment separation

| Environment | Purpose | Config template | Typical secrets source |
| --- | --- | --- | --- |
| **LOCAL** | Developer laptop | `.env.local.example` → `.env.local` or `.env` | Local `.env*` files (gitignored) |
| **DEV** | Shared development | `.env.dev.example` | CI/CD variables / secret vault |
| **TEST** | QA / UAT validation | `.env.test.example` | CI/CD variables / secret vault |
| **PROD** | Production | Use `.env.example` as checklist | Enterprise secret vault only |

Shared checklist template: `.env.example`

Frontend public API URL (no secrets):

- Local: `frontend/.env.example` → `frontend/.env`
- Packaged builds: `VITE_API_BASE_URL` build arg

---

## Required configuration (all environments)

### Application
- `APP_NAME`
- `APP_ENV` (`local` | `dev` | `test` | `prod`)
- `APP_HOST`, `APP_PORT`
- `LOG_LEVEL`
- `CORS_ORIGINS` (comma-separated)

### LLM
- `OPENAI_API_TYPE` (`azure` or `openai`)
- `OPENAI_API_KEY`
- `OPENAI_API_BASE` (LLM endpoint)
- `OPENAI_API_VERSION` (Azure)
- `OPENAI_DEPLOYMENT_NAME` / `OPENAI_MODEL`

### Embeddings
- `OPENAI_EMBEDDING_API_KEY` (optional; falls back to `OPENAI_API_KEY`)
- `OPENAI_EMBEDDING_API_BASE` (optional; falls back to `OPENAI_API_BASE`)
- `OPENAI_EMBEDDING_API_VERSION` (optional)
- `OPENAI_EMBEDDING_DEPLOYMENT_NAME` / `OPENAI_EMBEDDING_MODEL`
- `EMBEDDING_BATCH_SIZE`
- `EMBEDDING_PROVIDER` (leave blank in real environments)

### Vector database
- `CHROMA_PERSIST_DIRECTORY`
- `CHROMA_COLLECTION_NAME`

### BMI Hub crawl / auth session
- `CRAWLER_START_URL`
- `CRAWLER_ALLOWED_HOSTS` (optional if host can be derived from start URL)
- `CRAWLER_AUTH_DIR`
- `CRAWLER_STORAGE_STATE_PATH`
- other crawler limits (`CRAWLER_MAX_PAGES`, etc.)

### Frontend
- `VITE_API_BASE_URL` (public backend base URL; **no API keys**)

---

## 1. Build frontend

```powershell
cd frontend
Copy-Item .env.example .env
# Set VITE_API_BASE_URL to the backend URL for the target environment
npm ci
npm run build
```

Artifacts: `frontend/dist/`

Docker image:

```powershell
docker build `
  -f frontend/Dockerfile `
  --build-arg VITE_API_BASE_URL=https://REPLACE_WITH_BACKEND_PUBLIC_URL `
  -t bmi-chatbot-frontend:local .
```

---

## 2. Build backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Also install crawler/processor deps if this image/host will index content
pip install -r ..\crawler\requirements.txt
pip install -r ..\processor\requirements.txt
```

Run without Docker:

```powershell
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 3. Build Docker images

From repository root:

```powershell
docker build -f backend/Dockerfile -t bmi-chatbot-backend:local .
docker build -f frontend/Dockerfile --build-arg VITE_API_BASE_URL=http://localhost:8000 -t bmi-chatbot-frontend:local .
```

Local compose (uses `.env.local`):

```powershell
Copy-Item .env.local.example .env.local
# Fill secrets in .env.local
docker compose up --build
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173` (mapped to container port 80)

---

## 4. Configure environment variables

### LOCAL
1. `Copy-Item .env.local.example .env.local`
2. `Copy-Item frontend\.env.example frontend\.env`
3. Fill LLM/embedding keys and endpoints
4. Keep `CORS_ORIGINS=http://localhost:5173`

### DEV / TEST
1. Copy `.env.dev.example` or `.env.test.example` into your pipeline/secret store
2. Replace every `REPLACE_WITH_*` value
3. Use separate:
   - LLM endpoints/keys
   - embedding endpoints/keys (if different)
   - Chroma paths/collection names
   - CORS origins
   - BMI Hub URL / allowed hosts
4. Inject variables at deploy time (container env, platform app settings, Kubernetes secrets, etc.)

### PROD
Use the same variable names. Prefer:
- stricter CORS
- durable Chroma storage
- secret rotation
- no debug logging (`LOG_LEVEL=INFO` or `WARNING`)

---

## 5. Deploy backend

Platform-agnostic steps:

1. Build/push `bmi-chatbot-backend:<tag>`
2. Provide env vars from the DEV/TEST/PROD secret set
3. Mount/persist `CHROMA_PERSIST_DIRECTORY` (and optionally raw/processed data dirs)
4. Expose HTTP port `8000` (or platform equivalent)
5. Health check: `GET /health` (also `GET /api/health`)
6. Confirm OpenAPI: `GET /docs`

Example container run (placeholder values only):

```powershell
docker run -d --name bmi-chatbot-backend `
  -p 8000:8000 `
  --env-file .env.dev `
  -v REPLACE_WITH_DATA_VOLUME:/data `
  bmi-chatbot-backend:dev
```

---

## 6. Deploy frontend

1. Build with the correct public API URL:

```powershell
docker build -f frontend/Dockerfile `
  --build-arg VITE_API_BASE_URL=https://REPLACE_WITH_BACKEND_PUBLIC_URL `
  -t bmi-chatbot-frontend:dev .
```

2. Deploy static image/hosting (nginx in this Dockerfile, or any static host for `dist/`)
3. Ensure users can reach the frontend origin listed in backend `CORS_ORIGINS`

---

## 7. Configure CORS

Set `CORS_ORIGINS` to exact browser origins, comma-separated:

```text
https://dev-frontend.example,https://another-approved-origin.example
```

Rules:
- Include scheme + host (+ port if non-default)
- Do not use `*` with credentialed requests
- LOCAL uses `http://localhost:5173`
- DEV/TEST/PROD use their published frontend origins only

---

## 8. Configure authentication

### BMI Hub crawl authentication (content ingestion)
- Uses interactive Playwright login (no hardcoded username/password)
- Session storage path: `CRAWLER_STORAGE_STATE_PATH` (gitignored)
- Keep auth state off shared/public storage unless encrypted/controlled
- Re-auth when sessions expire: crawler `--reauth` / `.\scripts\crawl.ps1 -Reauth`

### Application/API authentication
- This release does not implement end-user SSO for the chat UI
- If your platform requires SSO/gateway auth in front of frontend/backend, configure it at the reverse-proxy / app-gateway layer
- Do not put LLM API keys in the React app

---

## 9. Populate vector database

On a secure worker/host with network access to BMI Hub and the configured embedding endpoint:

```powershell
# 1) Crawl
.\scripts\crawl.ps1 -InstallDeps -MaxPages 50

# 2) Process
.\scripts\process.ps1

# 3) Index (full rebuild or incremental)
.\scripts\index.ps1 -Mode full
.\scripts\index.ps1 -Mode stats
```

Ensure environment variables for embeddings and `CHROMA_*` point at the target environment’s storage.

For containerized backends, run indexing against the same persisted Chroma volume the API uses.

---

## 10. Run smoke tests

### Automated unit/build checks
```powershell
.\scripts\test.ps1
```

### Live integration checks (services up + index populated)
```powershell
.\scripts\verify-integration.ps1 `
  -BackendUrl https://REPLACE_WITH_BACKEND_PUBLIC_URL `
  -FrontendUrl https://REPLACE_WITH_FRONTEND_PUBLIC_URL `
  -Question "What information is available on BMI Hub?"
```

Minimum manual checks:
1. `GET /health` → `healthy`
2. Frontend loads
3. `POST /api/chat` returns `answer` and non-empty `sources` after indexing

---

## 11. Verify BMI Hub URLs

After chat responses:

1. Confirm each source `url` host is in `CRAWLER_ALLOWED_HOSTS` / start-URL host
2. Open several source links and confirm they resolve to real BMI Hub pages
3. Spot-check that cited sections match page content
4. Reject/fix any indexed content pointing outside allowed hosts

---

## 12. Rollback procedure

Keep rollback platform-agnostic:

1. **Record current release**
   - Image tags / build IDs currently serving DEV/TEST/PROD
   - Config version / secret version
   - Chroma data snapshot identifier (if available)

2. **Application rollback**
   - Redeploy previous known-good backend image tag
   - Redeploy previous known-good frontend image tag (built with the matching `VITE_API_BASE_URL`)
   - Keep previous CORS and secret versions unless the rollback requires the older config

3. **Data rollback (if a bad index was published)**
   - Restore the previous Chroma volume/snapshot to `CHROMA_PERSIST_DIRECTORY`
   - Or re-run `index.ps1 -Mode full` from a known-good processed dataset

4. **Verify**
   - `/health`
   - frontend load
   - one grounded chat with sources
   - sample BMI Hub source URLs

5. **Communicate**
   - Note rolled-back versions and any residual risks

---

## LOCAL vs DEV vs TEST vs PROD checklist

### LOCAL
- Use `.env.local` / `.env`
- Docker Compose or PowerShell scripts
- Interactive crawler login allowed
- Debug logging acceptable

### DEV
- Shared non-prod LLM/embedding endpoints
- Separate Chroma collection (`bmi_documents_dev` example)
- Restricted CORS to DEV frontend origin(s)
- Automate image deploy; manual/controlled crawl OK

### TEST
- Isolated secrets and collections (`bmi_documents_test`)
- Stable model deployments for repeatable QA
- Run `verify-integration.ps1` as release gate
- Prefer lower LLM temperature

### PROD
- Secrets only from vault
- Durable backups for Chroma
- Least-privilege network access to BMI Hub and model endpoints
- Change control + rollback tags required before promote

---

## Security reminders

- Never commit `.env`, `.env.local`, `.env.dev`, `.env.test`, `.env.prod`
- Never put API keys in frontend bundles
- Treat Playwright storage state as a credential
- Rotate LLM/embedding keys on schedule and after incidents
