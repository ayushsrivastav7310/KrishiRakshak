# Phase 3: disease detection

Implemented in the existing dashboard and FastAPI application. No authentication or farm-onboarding replacement.

## Runtime

- Model: https://huggingface.co/neghani/plantvillage-mobilenetv2
- Pinned revision: `d33601185b32cf05b3942661b8d84ffb86dc48ec`.
- Publisher-declared license: Apache-2.0. Files inspected: README, config, processor config, safetensors, calibration and threshold. No remote Python or pickled training arguments are loaded.
- Framework: Transformers/PyTorch MobileNetV2, 38 labels across 14 crop categories. Config supplies exact label order.
- Preprocessing: bundled PIL processor; shortest edge 256, center crop 224, RGB, rescale 1/255, mean/std 0.5. Softmax probabilities are returned without claiming calibrated diagnostic accuracy. Upstream calibration is retained for audit but not applied because its reported field pipeline differs.
- Model weights SHA-256: `f1a98e77629c36b5fe90a0fbed7ba56f097ce419c6dad8456bd135f36ea8d426`.

From repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-disease-inference.txt
.\backend\.venv\Scripts\python.exe backend/ml/fetch_disease.py
```

The pinned weights and six configuration/source files stay in ignored `backend/artifacts/disease-hf`. Metadata and checksums are generated in ignored `backend/artifacts/disease.json`. Reinstall these on a fresh checkout. Model loads lazily once per application instance; inference is serialized and runs off the async request loop. Missing, changed or incompatible artifacts return 503.

## API and UI

Authenticated `POST /api/diseases/predict` accepts multipart `crop` and `photo`. Supported JPEG/PNG/WebP, 5 MB, 20 megapixels; decode and MIME checks reuse Phase 2. Raw uploads are not persisted. GET endpoints: `/supported`, `/history`, `/model-info` under `/api/diseases`.

Dashboard includes crop selection, preview with URL cleanup, loading/error states, top prediction, alternatives, history, provenance and warnings. Confidence below 0.85, small top-two margin, crop mismatch, very small images or low intensity variation flags uncertainty. These are conservative heuristics, not a validated rejection system; arbitrary out-of-domain images can still receive confident classifications.

Curated descriptions/symptoms/prevention currently cover tomato early/late blight using UC IPM links. Other classes receive general observation and extension guidance, not disease-specific treatment. Complete expert-reviewed coverage remains pending. No pesticide dosage is generated.

## Evaluation and limitations

Real weights were executed locally on synthetic input and on one genuine public leaf through the authenticated upload flow; see `disease-smoke.json`. Neither is held-out evaluation. Upstream card claims lab accuracy but acknowledges leaf leakage, reports weak field results, and contains multiple evaluation revisions; these are not project validation metrics. Local accuracy, precision, recall, F1 and field performance remain unmeasured.

Training and evaluation tools: `backend/ml/train_disease.py`, `evaluate_disease.py`, `Phase_3_Disease_Training.ipynb`. See MODEL_TRAINING_REPORT.md. No new model was trained in this session.
