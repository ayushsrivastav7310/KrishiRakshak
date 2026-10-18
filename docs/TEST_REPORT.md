# Test report

Execution date: 2026-10-18. Final backend suite: **56 passed** (19 Phase 1, 20 Phase 2, 17 new Phase 3–5 tests); no skipped tests. Frontend: **9 passed**. Production build: passed.

Initial sandbox test attempt: 34 fixture errors and 5 passes due unwritable default pytest temp folder. Workspace basetemp resolved filesystem errors, but API test clients then hung during Windows asyncio socketpair creation. Faulthandler traced socket.accept before test requests. Those hangs are environment failures, not passing tests. Running the suite outside the sandbox with workspace basetemp succeeded.

Backend suite includes existing OTP/session/farm/photo ownership/security/schema-preservation tests and real Phase 2 soil/crop inference, weather parsing/failure and input validation tests. New tests cover disease missing artifact/upload validation/actual model output/history, irrigation formulas/rainfall/missing inputs/area validation/log history, mandi parsing/normalization/deduplication/empty data/staleness/net costs/MSP source rules/missing and rejected API credentials, and weather incomplete fields.

Frontend: 9 tests passed (6 existing CropIntelligence + 3 new farm-support tests). Covers missing-model disclosure, disabled analysis, farm area/location reuse, absent hydrological assumptions, and genuine-data empty states.

Production build executed successfully using `node scripts/vite.mjs build`. Python source compileall succeeded. FastAPI factory and lifespan exercised by tests. Live Open-Meteo probe succeeded. Pinned disease model real execution succeeded. Government no-key probe returned expected authorization error; no live authorized synchronization tested. A single genuine leaf upload smoke is recorded separately, not used as evaluation accuracy.

Not executed: fine-tuning, full held-out or field-photo evaluation, authorized government API filters/quotas, genuine MSP population, deployment load tests, independent browser visual QA. No such checks are marked passed.

Final backend command: `.\backend\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q --basetemp=.test-tmp-final5` (outside sandbox). Test collection confirmed 56 cases; run exited 0 at 100%, including after the backend/.env government-key configuration fix.

Final frontend commands: `node frontend/node_modules/vitest/vitest.mjs run --root frontend` (9/9), `node scripts/vite.mjs build` (1,582 modules, successful). The live irrigation adapter returned seven forecast days with precipitation/ET0 units mm; response saved in irrigation-weather-smoke.json. Genuine leaf upload returned Tomato___Early_blight, model confidence 0.996235191822052; this is one potentially training-overlapping smoke image, NOT measured accuracy. History persistence and owner isolation passed. Abandoned sandbox test runs were stopped after diagnostic evidence was recorded.
