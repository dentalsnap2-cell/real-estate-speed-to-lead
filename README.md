# real-estate-speed-to-lead
dentalsnap2-cell/real-estate-speed-to-lead
Real Estate Speed-to-Lead Engine
FastAPI webhook + structured AI lead qualification + transactional email/PDF + Slack hot-lead alerts + Streamlit agency console.
Architecture
`backend/main.py`: authenticated inbound webhook and FastAPI BackgroundTasks workflow.
`backend/ai_engine.py`: Pydantic v2 response model and OpenAI Structured Outputs (`.parse()`).
`backend/services.py`: Supabase or local SQLite persistence, PDF, Resend, Slack.
`dashboard/app.py`: pipeline, agency rules, and webhook simulator.
`supabase_schema.sql`: production PostgreSQL schema and seed settings.
Local setup (Python 3.11+)
```bash
git clone YOUR_REPOSITORY_URL
cd real_estate_speed_to_lead
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
Edit `.env`; set `AGENCY_API_KEY` to a long random secret. With no Supabase credentials the app uses local SQLite. With no OpenAI, Resend, or Slack credentials it uses mock AI/email/Slack output and still saves leads locally.
Terminal 1:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
Terminal 2:
```bash
streamlit run dashboard/app.py --server.port 8501
```
Open `http://localhost:8501`. API health: `http://localhost:8000/health`.
Manual webhook test:
```bash
curl -X POST http://127.0.0.1:8000/webhook/new-lead ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: change-this-to-a-long-random-secret" ^
  -d "{\"full_name\":\"Alex Morgan\",\"email\":\"alex@example.com\",\"phone\":\"+15550102000\",\"property_interest\":\"Downtown apartment\",\"inquiry_message\":\"I want to buy within 30 days with a budget of 650000.\"}"
```
On PowerShell, use `curl.exe` or submit through the Streamlit simulator.
Supabase
Create a Supabase project.
Open SQL Editor and run `supabase_schema.sql`.
In backend and dashboard environment, set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
Keep the service-role key only in trusted server environments. Never commit `.env`.
Railway deployment
Backend service
Push this folder to GitHub.
In Railway, create a project from the GitHub repository and add a service for the repository.
Set the service root directory to `/` (repository root).
Add variables from `.env.example` in Railway Variables. Set production Supabase, OpenAI, Resend and Slack credentials.
Set the start command to:
`uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
Generate a public domain. Verify `/health`.
Dashboard service
Add a second Railway service from the same GitHub repository.
Set start command to:
`streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port $PORT`
Add the same `AGENCY_ID`, `AGENCY_API_KEY`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`.
Set `API_BASE_URL` to the backend public URL (without trailing slash).
Generate a public domain for the dashboard.
Production hardening before onboarding paying agencies
This starter uses a single `AGENCY_ID` and a shared API key. For a real multi-agency SaaS, issue per-agency API keys, store only hashed keys, derive tenant identity from the authenticated key, and enforce tenant-scoped RLS/policies.
FastAPI `BackgroundTasks` run in the web process and are not durable across restarts. For reliable production delivery, move processing to a queue (Celery/RQ/Arq + Redis) and add retries, dead-letter handling, idempotency keys, and delivery event logs.
Add dashboard authentication (e.g. Supabase Auth), role-based access, rate limiting, request size limits, audit logs, retention/deletion controls, monitoring, and alerting.
Configure a verified sender domain in Resend and comply with local privacy, consent, and marketing-email rules. This code sends a transactional response to an inbound enquiry.
The generated PDF is a personalized enquiry brief, not a property-specific brochure or listing catalogue. Add approved property inventory data before making property claims.
Configure CORS only for known form providers if browser-based direct submission is required. Server-to-server webhook calls do not require permissive CORS.
Validate actual provider delivery in staging. Mock mode is for local functional testing only.
