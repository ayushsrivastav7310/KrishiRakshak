# Phase 2 implementation report

Verified on 18 October 2026 (Asia/Kolkata). **Core implementation is running; full scientific/field acceptance is not claimed.** Soil fine-tuning and independent soil evaluation remain pending, and the crop dataset leaves NPK units and rainfall period unspecified.

## Repository inspection and implementation plan

The existing project contained React 19, Vite, Tailwind, FastAPI, SQLite, JWT cookie sessions, OTP demo authentication, farmer onboarding, farm editing, private photo storage and a dashboard. PostgreSQL was not configured. No repository AGENTS.md was found in the inspected workspace. Phase 1 architecture and data were preserved.

The implemented plan was to add modular authenticated inference/weather/history APIs, verify model/dataset contracts, train a reproducible crop baseline, add Crop Intelligence within the existing dashboard, and run API, component, build and browser checks. PostgreSQL migration was not introduced because it would replace the actual existing database architecture.

## Features implemented

- Soil upload validation: decoded JPEG/PNG/WebP content, matching MIME, maximum 5 MB and 20 megapixels; malformed/decompression-heavy inputs rejected. New analysis uploads are not persisted.
- Actual local inference using the requested Hugging Face weights; three supported visual categories, confidence score, uncertainty below 0.70 and explicit closed-set limitations. This threshold is a UI heuristic, not a calibrated detector.
- Manual soil entry/correction stored as a separate record linked to an owner-checked analysis. Farm texture categories remain distinct.
- Random Forest crop classification with ranked alternatives, accurately labeled vote shares, saved exact inputs/provenance/model version, observed dataset range rejection and general verification considerations.
- Open-Meteo current temperature/humidity/rain plus seven-day forecast, location controls, timestamps, units and attribution. Weather autofills temperature/humidity only; manual edits remain possible. Forecast rainfall never replaces dataset rainfall.
- Responsive dashboard section, image preview, loading/error states, manual source labels, metadata availability and latest 50 owner-only history entries.
- Additive SQLite history migration, owner isolation, persistence across backend restarts, existing cookie authentication and Origin/CSRF rules. Existing onboarding and private farm-photo behavior remains available.
- Missing/corrupt/incompatible models return clear 503 responses; no mock predictions or automatic artifact downloads at request time. Models load once per process with inference locking and threadpool execution.

## Models, datasets and methods

### Crop — trained and evaluated

Source: [Atharva Ingle crop dataset](https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset), version 1, Apache 2.0 as reported by Kaggle's public metadata. Actual CSV: 2,200 rows; 22 classes; 100 examples per class; zero missing values, identical feature duplicates or conflicting identical-feature labels. Dataset digest and labels are recorded in `docs/crop-evaluation.json`.

Validation rejects missing, Boolean, nonfinite and invalid values; the training script fails clearly rather than silently imputing an unreviewed dataset. Duplicate removal precedes splitting. Seeded stratified split: 1,760 training / 440 independent test rows, seed 42. Fixed baseline: 300-tree Random Forest; comparison: most-frequent-class DummyClassifier. No scaling or feature transformation beyond numeric conversion. Feature order: N, P, K, temperature, humidity, pH, rainfall. Soil type is not a feature.

| Actual held-out metric | Random Forest | Majority-class baseline |
| --- | ---: | ---: |
| Accuracy | 0.9931818182 | 0.0454545455 |
| Macro F1 | 0.9931775542 | 0.0039525692 |
| Correct predictions | 437 / 440 | 20 / 440 |

Per-class precision/recall/F1/support and both confusion matrices are in `docs/crop-evaluation.json`; labeled Random Forest matrix: `docs/crop-confusion-matrix.csv`; exact split: `docs/crop-split.json`. Saved local artifacts: `backend/artifacts/crop.joblib`, `crop.json`. Actual environment: Windows 11, Qualcomm ARMv8 host, Python 3.12.14, scikit-learn 1.9.1, CPU execution. Epochs are not applicable to Random Forest. Execution timing is recorded in the JSON report. Repeated runs returned the same held-out metrics.

These metrics describe this dataset's random holdout classification only. No geographic/seasonal field validation or yield improvement was measured. NPK are described by the source as ratios without units; rainfall mm lacks a time period. The UI and model metadata disclose both, and no conversion from kg/ha, ppm or mg/kg is performed.

### Soil — real inference, fine-tuning pending

Requested source: [Hugging Face model](https://huggingface.co/shrutmpatil/soil-classification-model), MIT. Actual revision, checksum and encoder evidence: `docs/soil-model.json`; license notice: `docs/SOIL_MODEL_LICENSE.txt`. Classes in verified order: Medium Black Soil, Reddish Brown Soil, Saline Soil.

The downloaded file is **VGG16-style**, despite the model card's MobileNetV2 description. HDF5 layer inspection confirmed convolution blocks, flatten and dense head. Inference follows the publisher's file-picker path: OpenCV BGR → bilinear 224×224 → float32 /255. The publisher's original VGG training/data path agrees; other code paths conflict. Exact weight training provenance and preprocessing linkage have not been independently verified. Metadata and prediction limitations disclose this uncertainty.

The requested MobileNetV2 transfer-learning workflow is supplied separately as `backend/ml/train_soil.py` and the standalone **unexecuted** `Phase_2_Soil_Training.ipynb`. It loads ImageNet weights, adapts the head, audits image integrity/size, reports class counts and duplicate/near-duplicate/conflicting-label groups, generates contact sheets, retains one representative per detected duplicate component, and creates seeded stratified 70/15/15 train/validation/test splits. Training-only augmentation, class weighting, a frozen-head stage, selective layer fine-tuning, frozen batch normalization, early stopping, global best validation checkpointing, independent final testing and actual hardware/epoch/metric reports are implemented.

Selected research dataset: [Phantom-fs original soil images](https://github.com/Phantom-fs/Soil-Classification-Dataset), **CC-BY-NC-4.0**; commercial use requires separate permission. Seven distinct categories are documented without a mapping to the three-class model. No source images or derivative weights from that dataset are included. Actual image audit, manual label/quality review and fine-tuning were **not executed**. Therefore soil training image count, trained epochs, independent accuracy, precision/recall/F1 and confusion matrix are **not available**. Publisher metrics were not reused as local results. See `docs/DATASETS.md` for license details and attribution.

## Actual verification

| Check | Result |
| --- | --- |
| Complete Python API suite | **39 passed**, final run 6.79 seconds; includes all 19 Phase 1 tests |
| React component suite | **6 passed**: availability/errors, image validation, loading/failure, weather autofill/editing, results/input payload |
| Vite production build | **Passed**, 1,581 transformed modules |
| Headless Edge browser against isolated real FastAPI server and built frontend | **8 checks passed**, no page errors |
| Live Open-Meteo request for Lucknow | **Passed**, actual response saved in `docs/weather-smoke.json` |
| Soil weight loading and inference | **Passed** on generated brown PNG; validates execution, not recognition accuracy |
| Crop pipeline repeatability | **Passed**: same held-out accuracy/F1 on repeated training runs |

Backend coverage includes soil content/type/size/pixel validation, model absence/corrupt metadata, real soil and crop endpoints, invalid inputs, bounds, weather failure/response mapping, owner-isolated correction/history, database restart persistence, Phase 1 login/OTP/farm/photo/CSRF/session behavior and API docs. Browser checks include login, dashboard, real crop inference, real soil inference, manual correction, live weather preserving rainfall, history/session reload, 390px layout without horizontal overflow, and logout. The saved browser report groups these into eight checks: `docs/browser-smoke.json`. The mobile screenshot was visually inspected.

Initial attempts exposed a sandbox temp-folder failure and excessive pytest parameter IDs on Windows; these were corrected before the final passing run. Frontend tests initially found input accessible names incorporating provenance text; explicit input labels fixed that. Final runs have no failing critical checks. CPU/ML imports were slow under sandbox execution; full inference and final suites were verified outside that restriction. Full MobileNet training remains unexecuted, not counted as passed.

## Remaining limitations and pending work

1. Confirm permitted soil dataset use, download originals, execute the notebook audit, visually review all classes, train MobileNetV2 and publish actual independent metrics before claiming fine-tuning success.
2. Resolve the pretrained model-card/weight discrepancy and independently evaluate its exact preprocessing, calibration and out-of-distribution behavior. Unsupported soil/non-soil images can receive high scores.
3. Obtain a crop dataset with verified laboratory units and rainfall time windows, or validate those semantics with the publisher. Present classifications as exploratory until field verification is available.
4. No PostgreSQL server was present or tested; storage remains the working existing SQLite database. No Phase 3 features were implemented.
5. New ML history is limited to the most recent 50 entries in the API; retention/deletion policy and production performance testing remain deployment concerns. Full soil training, commercial licensing clearance and field agronomic validation are outside the verified results above.

Setup, reproduction commands and API contracts: `docs/PHASE_2_SETUP.md`. Large weights/datasets remain local and ignored by Git; they are not silently bundled or committed.
