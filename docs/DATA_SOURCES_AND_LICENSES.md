# Sources and licensing audit

Checked 2026-10-18.

| Source | Finding / use |
|---|---|
| https://huggingface.co/neghani/plantvillage-mobilenetv2 | Model card declares Apache-2.0; pinned safetensors/config downloaded and checksummed. Model card retained locally with artifact. Dataset rights are separate from model declaration. |
| https://github.com/spMohanty/PlantVillage-Dataset | Original image dataset, leaf-map/grouping and official grouped split guidance inspected. Only one color image downloaded into ignored data for a smoke test. |
| https://huggingface.co/datasets/mohanty/PlantVillage | Dataset card declares CC-BY-SA-3.0. Preserve credit to Mohanty, Hughes and Salathé, citation DOI 10.3389/fpls.2016.01419, and applicable share-alike terms. Full dataset not redistributed. |
| https://open-meteo.com/en/docs | Official forecast field names/units checked and live request tested. Attribute Open-Meteo. Confirm current service terms and deployment entitlement before commercial hosting; free availability is not unlimited access. |
| https://www.fao.org/4/x0490e/x0490e00.htm | Scientific reference for ETc/Kc and water depletion; implementation explicitly documents simplified assumptions. No FAO text/dataset bundled. |
| https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi | Official candidate source confirmed as a catalog page. API requires credentials; authenticated access/quotas/usage terms not verified. Import only official records permitted for reuse; preserve source provenance. |
| https://agmarknet.gov.in/ and https://enam.gov.in/ | Reference portals; no scraping, authenticated connector or buyer offers implemented. |
| https://desagri.gov.in/ | Intended official MSP source. No notification or prices silently assumed; operator must verify each imported notification and period. |
| https://ipm.ucanr.edu/agriculture/tomato/early-blight/ and https://ipm.ucanr.edu/agriculture/tomato/late-blight/ | Short original paraphrases of symptoms/general prevention; links retained. No treatment table or dosages copied. Local extension confirmation required. |

Additional field-image datasets were not downloaded or used. Upstream mentions PlantDoc; its claims do not establish a locally evaluated field model. Runtime metrics are intentionally null until local evaluation.
