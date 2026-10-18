# Integration report

## Audit and plan executed

Existing app: Vite/React 19, lucide icons, CSS theme, state-based pages in main.jsx, shared fetch wrapper, CropIntelligence panel and FarmSummary. Backend FastAPI factory, SQLite connection with lock, JWT session cookies, OTP authentication, origin/body/rate middleware, farm JSON/profile storage. Phase 2 uses local sklearn crop and TensorFlow soil models plus a fixed Open-Meteo endpoint. Existing model artifacts were present. No AGENTS.md found in the repository. Substantial Phase 2 working-tree changes were preserved.

Plan: additive disease model/API/training tools; irrigation water balance/API; government observations/import/MSP/comparison; dashboard panels; regression verification and honest reports. Modules share farm area/location/farmer-selected soil and previous crop as a suggested selection to confirm. Farm profile has no current-crop entity or multiple fields, so these were not invented or migrated silently.

## New API groups

- Disease: GET supported, history, model-info; POST predict (multipart crop/photo).
- Irrigation: GET weather, recommendations, history; POST calculate, log.
- Mandi: GET prices, markets, commodities, history, msp, sync-status; POST compare, sync.

All routes under `/api`, authenticated with existing dependency; mutations retain existing origin checks. All numeric request models reject nonfinite input. Image upload uses existing bounded middleware and decoder. External API URLs fixed; no user-selected fetch URL. SQL values parameterized. Expensive prediction/sync/calculation routes throttled. Government key never reaches frontend. Secrets are not logged.

Additive tables: phase_migrations, farm_events with user ownership/date, mandi_prices with unique observation key and original source JSON, msp_records with exact crop/variety/season and verified period columns. Existing users/farms/OTP/Phase 2 tables untouched. Migration is idempotent. JSON events store model version, water recommendation snapshots and irrigation records. Historical API results are limited to 100 events; advanced pagination pending.

## Dependencies and setup

Existing setup remains `run-local.cmd setup`, `run-local.cmd`, `run-local.cmd build`, `run-local.cmd test`.

Disease inference dependencies: `pip install -r backend/requirements-disease-inference.txt`, then `python backend/ml/fetch_disease.py`. These were installed and pinned weights downloaded locally. Training dependencies are separate in requirements-disease.txt. New optional env: DATA_GOV_API_KEY in backend/.env. Existing JWT/OTP/database/origin env configuration unchanged.

External probes: pinned Hugging Face metadata/card/files and weights succeeded outside restricted sandbox; Open-Meteo live forecast succeeded, ET0/rainfall mm verified; Data.gov unauthenticated HTTP 400 Authorization field missing. No authorized government filter or real synchronization was claimed. No MSP notification imported. Source quota and usage verification remain pending credentials.

## Material limits

Fine-tuning/held-out evaluation, complete disease guidance coverage, genuine mandi/MSP population, complete source paging, historical water reconstruction, multiple-field UX and independent browser visual QA remain pending. Frontend charts use native SVG for genuine observations; no new chart-library dependency needed. No marketplace, synthetic market data, sensor readings or pump actions introduced.
