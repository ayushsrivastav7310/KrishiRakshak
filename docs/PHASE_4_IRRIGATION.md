# Phase 4: irrigation

Implemented authenticated weather, calculate, recommendations, log and history endpoints under `/api/irrigation`. Dashboard reuses profile location, area and farmer-selected soil type. Converts hectares × 10,000 and acres × 4,046.8564224 to square meters. Current profile only stores previous crop, so the farmer must confirm the selected current crop and planting date. One existing farm is modeled as `fieldId=main`; API accepts field IDs but multi-field profile management remains future work.

## Method

Reference: https://www.fao.org/4/x0490e/x0490e00.htm (FAO-56, indicative single crop coefficients).

`ETc = Kc × ET0`; `TAW = 1000 × (field capacity − wilting point) × root depth`.

Daily depletion is clamped to `[0, TAW]` after crop consumption minus 80% of forecast rain. Irrigation is suggested when depletion reaches 50% of TAW, replacing the estimated depletion. Gross depth is net depth / application efficiency. `liters = gross millimeters × m²`. Later calendar days assume each prior suggested irrigation occurs; the recommendation shows the first trigger. Volumes are estimates, not pump commands.

Only maize, wheat and tomato have indicative Kc schedules. Assumed season lengths are 125/150/135 days; stage boundaries are 20/40/80% of season. Maize Kc initial/mid/end 0.3/1.2/0.6; wheat 0.3/1.15/0.3; tomato 0.6/1.15/0.8. Stage durations, fixed depletion fraction, effective rain and efficiency are planning assumptions, requiring local calibration. Beyond the assumed season, quantity is withheld.

No field capacity, wilting point or infiltration is inferred from photographs or soil labels. Quantity requires field capacity, wilting point, effective root depth and current depletion or measured root-zone moisture. Missing essentials yield forecast plus warnings and null quantity/date. These properties must come from measurement or agronomic assessment. SoilGrids is not integrated.

Current water status is today's assessment before the entered recent irrigation. A last-irrigation date alone cannot reconstruct depletion. Saved logs are retained for accounting; users must update today's water status. Logs are not silently replayed into the calculation, avoiding double counting. Historical multi-day water-balance reconstruction is pending.

## Weather and persistence

Reuses the existing Open-Meteo provider and leaves Phase 2's endpoint behavior intact. Separate irrigation adapter requests daily `precipitation_sum`, `et0_fao_evapotranspiration`, current temperature/humidity/wind and hourly surface moisture, soil temperature and solar radiation. Validates daily finite nonnegative mm values. 12-second timeout, 15-minute bounded coordinate cache, explicit 502 on incomplete weather. Live units verified on 2026-10-18 near Lucknow. Forecast availability varies geographically.

Surface soil moisture is a model output, not a root-zone measurement and is never substituted for measured water status. UI displays forecast planning calendar, recommendation warnings, manual irrigation logs and usage/recommendation histories. API retains current/hourly weather; a richer hourly weather visualization remains pending.

Records are user-owned JSON events in additive SQLite migration. IoT is not required or implemented; future sensor observations should provide timestamp, units, field ID, device identity and calibration before feeding current status. Pump control is outside scope.
