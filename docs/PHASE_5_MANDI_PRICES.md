# Phase 5: mandi observations

Implemented price filters, pagination, reporting/stale labels, market/commodity listings, history, genuine-observation chart, optional server-side sync, MSP lookup and cost comparison. Existing dashboard theme and authentication are reused. No buyer marketplace or forecast model is added.

## Government access status

Candidate endpoint: https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070

Live unauthenticated probe returned HTTP 400, `Authorization field missing`. A valid `DATA_GOV_API_KEY` has not been supplied. Authenticated schema, actual state/commodity filter behavior, entitlement, quotas and permitted deployment use are therefore NOT verified. Daily source title describes expected reporting frequency, not a guarantee of every market reporting each day. Runtime adapter uses documented candidate fields and explicit source errors; mock tests validate the adapter contract, not live government access.

Set `DATA_GOV_API_KEY` in backend/.env only; click Sync government data. The key stays server-side. Sync uses fixed URL, 15-second timeout, at most one retry for 429/502/503/504, 15-minute filter-scoped cache and request throttle. At most 1,000 rows are ingested per sync, clearly labeled partial coverage. Complete source pagination and a scheduled sync job remain pending. Existing observations remain accessible during outages.

## Explicit CSV fallback

Download permitted genuine CSV data from the official OGD/AGMARKNET portal. Do not relabel arbitrary prices as government data. Operator command (not a public ingestion endpoint):

```powershell
.\backend\.venv\Scripts\python.exe backend/ml/import_markets.py official.csv --database backend/data/krishi.sqlite --unit INR/quintal
```

Required headers: `state,district,market,commodity,variety,arrival_date,min_price,max_price,modal_price`. Dates accept DD/MM/YYYY or ISO. Supported units INR/quintal and INR/kg; kg values multiply by 100. Invalid/nonfinite/negative/range-inconsistent/future observations reject the transaction. Original values/units and synchronization timestamps are preserved. Unique market/commodity/variety/date/source key makes repeated imports idempotent; corrected observations update in place. Full revision history is not implemented.

No CSV or fake observations are seeded. Prices older than two days are flagged stale. Latest-date-first tables do not imply prices are live. Chart requires at least two distinct reporting dates for the same state/district/market/commodity/variety; no synthetic points or future estimates. Daily/weekly/monthly aggregation summaries remain pending.

## MSP

No unverified MSP amounts are bundled. Import a manually verified official notification CSV:

```powershell
.\backend\.venv\Scripts\python.exe backend/ml/import_markets.py official-msp.csv --database backend/data/krishi.sqlite --msp
```

Headers: `crop,variety,season,price,unit,source,period_start,period_end`. Period boundaries must be copied/verified from the applicable notification; do not infer them from a crop photograph or a generic year. Unit must be INR/quintal, source must be HTTPS on gov.in/nic.in. Domain validation is not a substitute for operator verification of the document. Endpoint matches exact crop/variety/season. With priceId, a difference is returned only when the observation date is within the supplied marketing period. MSP is not a universal private-sale floor or guaranteed purchase price.

## Selling costs

Comparison uses stored observation IDs, quantity in quintals, farmer-estimated total trip distance, trip transport cost per km and other selling costs. Same commodity and variety required. `gross = modal × quintals`; `net = gross − distance × trip-cost/km − handling`. All dates and stale flags remain visible. No map-derived distances are invented. Confirm actual buyer terms, grade and missing costs before selling.
