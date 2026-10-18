# Phase 2 setup and API

The existing React/Vite frontend, FastAPI application, cookie authentication and SQLite database remain in use. PostgreSQL was not configured in this repository; no database engine migration was made. Schema initialization adds `intelligence_history` and its owner index idempotently, including when opening an existing Phase 1 database. Back up the database before deploying any schema change.

## Run in this workspace

The ML dependencies, downloaded soil weights and trained crop artifact are already present locally. Restart the backend to load them, then use Crop Intelligence below the farm summary:

```powershell
.\run-local.cmd
```

Models are loaded once per process. Restart after replacing artifacts. Phase 1 still starts if an artifact or optional ML dependency is missing; inference returns 503 without fabricated results.

## Reproduce on another machine

From the project root, with Python 3.12 and Node installed:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-ml.lock.txt
npm install
# Configure backend/.env as described in README.md.
.\backend\.venv\Scripts\python.exe backend/ml/fetch_sources.py
.\backend\.venv\Scripts\python.exe backend/ml/prepare_soil.py
.\backend\.venv\Scripts\python.exe backend/ml/train_crop.py
.\run-local.cmd
```

The ML lock records the actual Windows environment; TensorFlow wheel support varies by OS and architecture. For Colab use the notebook's Linux TensorFlow installation. `requirements-ml.txt` contains direct ML dependency pins plus the existing API requirements. The original Phase 1 lock remains unchanged.

`fetch_sources.py` checks Kaggle's license metadata before downloading the CSV, pins the soil download to the resolved Hugging Face commit, retains source descriptions and preprocessing evidence, and never extracts arbitrary archive paths. Network access is required. `prepare_soil.py` checks the weight digest and reads the class encoder's known UTF-32 array layout without unpickling. Third-party pickle files are never executed. Only the project's own locally trained crop joblib is loaded. Large artifacts and datasets are ignored by Git. Preserve `docs/SOIL_MODEL_LICENSE.txt` with redistributed model copies.

## Train and evaluate

Crop: `train_crop.py` validates the schema, finite values, label consistency, duplicates and license, then performs a seeded stratified 80/20 split. A fixed 300-tree Random Forest and majority-class baseline are evaluated on the same held-out test set. Outputs: `backend/artifacts/crop.joblib`, `crop.json`, `docs/crop-evaluation.json`, `crop-split.json` and `crop-confusion-matrix.csv`. Feature order, units, supported labels, ranges, dataset hash and preprocessing are recorded. No yield claims follow from these metrics.

Soil: open `backend/ml/Phase_2_Soil_Training.ipynb` in Google Colab. It contains the full standalone training script and instructions to review the noncommercial license, clone only the selected source, audit originals, inspect all contact sheets and resolve labeling conflicts. The notebook is unexecuted. The script can also be run locally:

```powershell
# Only after confirming the CC-BY-NC-4.0 conditions apply to your use:
.\backend\.venv\Scripts\python.exe backend/ml/train_soil.py PATH_TO_ORIGINAL_CLASS_FOLDERS --output backend/data/soil-training --noncommercial-research --audit-only
# Review contact sheets and audit.json; correct quality and labeling problems first.
.\backend\.venv\Scripts\python.exe backend/ml/train_soil.py PATH_TO_ORIGINAL_CLASS_FOLDERS --output backend/data/soil-training --noncommercial-research --reviewed
```

No mapping is applied between the seven-class dataset, three-class pretrained model and texture-based farm profile. Fine-tuned models and metadata are separate outputs; do not replace the deployed classifier without reviewing their license, evaluation and labels.

## API contracts

Interactive schemas: `/docs`, machine-readable schemas: `/openapi.json`. All Phase 2 routes require the existing session cookie. Mutations also require `Origin` to exactly match `APP_ORIGIN`. Same-origin Vite proxy behavior is unchanged. Errors use `{"error":"message"}`, with `fields` for validation errors. Invalid inputs return 400; unsigned sessions 401; CSRF failures 403; missing owner records 404; unavailable models 503; failed or malformed weather upstream responses 502.

| Method and route | Request | Response |
| --- | --- | --- |
| POST `/api/soil/predict` | Multipart `photo`: decoded JPEG/PNG/WebP, <=5 MB, <=20 MP | `id`, `soilType`, `confidence` (0–1 softmax score), `uncertain`, supported classes, limitations, model version |
| POST `/api/soil/correction` | JSON `analysisId`, `soilType` | Owner-checked manual confirmation linked to the original analysis |
| POST `/api/crops/recommend` | JSON `N`, `P`, `K`, `temperature`, `humidity`, `ph`, `rainfall`; optional soil type and provenance fields | Recommended crop, top three class vote shares, exact inputs, model version, limitations, saved ID |
| GET `/api/weather` | `latitude` (-90–90), `longitude` (-180–180) | Open-Meteo current estimates, timestamps, timezone, units and seven-day daily forecast; rainfall caveat |
| GET `/api/crops/supported` | None | Supported crop labels, feature order, units and dataset ranges |
| GET `/api/models/metadata` | None | Availability, model versions, source/license, hashes, preprocessing and limitations |
| GET `/api/intelligence/history` | None | Latest 50 owner-only soil/crop/correction records, newest first, UTC timestamps |

Crop numerical constraints: N/P/K 0–1000, temperature -50–65 °C, humidity 0–100%, pH 0–14, rainfall 0–10000 mm. Inference additionally rejects values outside the observed dataset ranges. Missing, nonfinite, Boolean and extra crop parameters are rejected. Soil type is stored but **not used** as a crop model feature.

Provenance fields: `soilSource` = `farmer-provided` / `image-estimate`; `nutrientSource` = `farmer-provided` / `soil-test`; `temperatureSource` and `humiditySource` = `farmer-provided` / `weather-estimate`; `rainfallSource` = `farmer-provided` / `historical-record`. Defaults are farmer-provided. The frontend allows marking NPK/pH as measured only after dataset compatibility has been independently verified; no conversion is performed.

NPK units and rainfall accumulation period are **unspecified by the crop publisher**. Inputs use dataset-scale NPK; mg/kg, ppm and kg/ha cannot be treated as equivalent. This is a dataset classifier for exploration, not a scientifically validated prescription engine. Weather autofill sets temperature and humidity only, marks them as weather estimates and allows editing. Rainfall remains a separate manual input. Current weather is not a growing-season average.

New soil endpoint images are processed in memory and never stored. The original Phase 1 optional private photo storage remains unchanged. History stores only JSON inputs/results and model versions, never image bytes.

## Tests

```powershell
.\run-local.cmd test
.\run-local.cmd test-frontend
.\run-local.cmd build
```

In restricted Windows environments, supply a writable temporary path: `python -m pytest -c backend/pytest.ini backend/tests --basetemp=backend/data/pytest-local`. Full integration tests require the local artifacts prepared above. Missing-model behavior has separate explicit tests.

`scripts/phase2-browser-smoke.mjs` runs against an **isolated** test backend at `127.0.0.1:8011`. Configure `APP_ORIGIN=http://127.0.0.1:8011`, `DATABASE_PATH=data/phase2-browser.sqlite`, `UPLOAD_DIR=data/phase2-browser-uploads`, `DEMO_AUTH=true`, `DEMO_OTP=654321` in that server process only. Build the frontend first. Install Playwright and its Chromium browser, or set `PLAYWRIGHT_CHANNEL=msedge` for installed Edge. Set `PLAYWRIGHT_MODULE` only when Playwright is outside normal Node resolution. Create a 224px brown PNG at `backend/data/ml/browser-soil.png`; it is an inference smoke fixture, not an evaluation image. The smoke script creates only a test farmer in that isolated DB. Do not run against production data.
