# KrishiRakshak — Phase 1

Farmer-focused **React + Vite + Tailwind** frontend and **Python + FastAPI** backend with SQLite, JWT cookie sessions and private soil photos. The Express backend has been replaced. Existing SQLite records, uploaded files, OTP hashes and JWT sessions remain compatible with the same secret.

## Start on this Windows workspace

The Python virtual environment and dependencies are already prepared. From the project root:

```powershell
.\run-local.cmd
```

This starts the React frontend at **http://127.0.0.1:5173** and FastAPI at **http://127.0.0.1:8000**. The launcher finds the available Node runtime and the Python virtual environment without requiring npm on PATH or PowerShell script activation. Press Ctrl+C to stop both processes. Stop any older running launcher before starting the migrated version.

Demo authentication uses the six-digit code in `backend/.env` (currently `123456`). No SMS is sent. The app displays a Demo authentication label, and production refuses demo mode.

Run separately, without activating a PowerShell script:

```powershell
# Frontend — project root
.\run-local.cmd frontend

# Backend — a second terminal, project root
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

If your Python environment is already activated, the backend command is simply `uvicorn main:app --reload` from `backend/`. API documentation: **http://127.0.0.1:8000/docs**. The exact Origin check applies to documentation's interactive mutations too; they require setting APP_ORIGIN to the backend URL instead of the Vite URL. Keep the default origin for normal frontend use.

## Fresh setup

Use Python 3.12 or newer and Node.js LTS for the React frontend. Python virtual environments are local to a machine; recreate them after moving the project.

```powershell
# Project root: install frontend dependencies
npm install

# Create backend/.venv and install the pinned Python dependencies
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
```

Alternatively, `.\run-local.cmd setup` creates the Python environment and installs `backend/requirements.txt` when a Python interpreter is available. Dependency ranges are listed in `requirements.txt`; `requirements.lock.txt` records the exact versions used for verification.

Copy `backend/.env.example` to `backend/.env` and replace JWT_SECRET with a random secret of at least 32 characters. The combined launcher generates a local secret if the environment file is missing. Never commit `.env`, `.venv`, the database or uploads. For the demo, explicitly set `DEMO_AUTH=true` and a six-digit `DEMO_OTP`.

After setup, `npm run dev` from the root starts **only the frontend**, matching `cd frontend; npm run dev`. Start the Python backend separately with Uvicorn, or use `.\run-local.cmd` to run both.

## Build and tests

```powershell
.\run-local.cmd build
.\run-local.cmd test
```

With Node on PATH, `npm run build` also builds the frontend. From `backend/`, `.\.venv\Scripts\python.exe -m pytest` runs the API tests.

To serve the compiled frontend and API from FastAPI, build first, set `APP_ORIGIN=http://127.0.0.1:8000` in `backend/.env`, then run Uvicorn and open that URL. Use one HTTPS origin and secure cookies in production. Use 127.0.0.1 consistently; switching to localhost changes the origin.

## Layout

```text
frontend/
  src/                 React screens, API client, farm summary and styles
  package.json         Frontend dependencies and scripts
  vite.config.js       Proxies /api to FastAPI on port 8000
backend/
  main.py              Uvicorn ASGI entry point
  app/
    api.py             Authentication, farm and private photo endpoints
    config.py          Environment and path configuration
    database.py        SQLite schema and access
    models.py          Pydantic request validation
    otp.py             Phone normalization, OTP hashes and SMS adapter boundary
    security.py        CSRF origin checks, request limits and auth throttling
  tests/               Pytest API and migration tests
  requirements.txt     Direct dependency ranges
  requirements.lock.txt Exact tested Python versions
  .env.example         Configuration template
  data/                Ignored database and owner-protected uploads
scripts/
  manage.py            Python launcher for development, setup, build and tests
  vite.mjs             Frontend CLI resolution for npm and pnpm
run-local.cmd          Windows launcher; no execution-policy changes needed
```

Paths for SQLite and uploads resolve relative to `backend/`, regardless of the terminal's working directory. Tables and upload folders are created automatically. Tests use isolated temporary databases and files.

## Phase 1 behavior

Welcome → phone → OTP → four onboarding steps → dashboard. Returning users with a saved farm go directly to the dashboard, and sessions survive refresh. My Farm edits the account's single saved farm. Onboarding values survive back/next navigation; unsaved values remain in memory and are lost on a full reload.

Location accepts village/district/state or a complete coordinate pair. GPS is requested only by an explicit button. Optional soil-test values validate pH between 0 and 14 and require a unit for NPK values. Photos can be previewed, replaced and removed; uploads accept valid JPEG/PNG/WebP images up to 5 MB. Pillow verifies the file format and image integrity without inferring soil or nutrient information.

The four dashboard cards are clearly labeled Coming soon. They produce no fake recommendations, weather, disease detections, prices or buyer transactions.

## Security and prototype boundaries

- OTP challenges store HMAC digests, expire after five minutes, impose a 60-second resend cooldown and five-attempt limit, and are consumed on success. Auth routes have per-IP request limits.
- JWT sessions last seven days in HttpOnly, SameSite=Strict cookies. Production cookies use Secure. Mutations require the exact APP_ORIGIN for CSRF protection. Vite's API proxy keeps browser requests on the frontend origin.
- Set `APP_ENV=production` for production; `NODE_ENV=production` is supported for compatibility. Demo authentication is forbidden in production. Real SMS is intentionally unconfigured and returns 503; implement the adapter in `backend/app/otp.py` before real authentication is possible. No OTP or token logging is added.
- Photos live outside the public build directory, use random filenames and are returned only after checking the session's owner. Uploaded images are verified but not re-encoded or scanned.
- SQLite and local uploads target a single server. Rate limits are process-local and reset on restart. Use durable storage, backups, HTTPS, a real SMS provider and explicit trusted-proxy configuration before deploying.
- Logout clears the cookie; a copied JWT remains valid until expiry. Rotate the secret to invalidate all sessions.
- Farm details save before an optional photo upload; upload failure preserves the form and displays a retry message.

## Verification

The Python suite covers login, cookies, OTP failure/expiry/cooldown/attempt limits, validation, farm save/edit, owner isolation, image integrity/type/size limits, CSRF, request rate limits, session restoration, logout, production guards, existing database/JWT compatibility across restarts, API documentation and static frontend serving. Frontend build is checked separately. GPS permissions and a real SMS provider are not exercised.

Verified after migration: 19 Python tests passed, the frontend production build passed, and the browser flow through Vite to FastAPI completed demo login, farm onboarding/save, session restoration after refresh, and logout. Browser test data was removed afterward.

