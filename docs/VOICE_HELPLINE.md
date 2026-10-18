# AI Voice Helpline

## Implementation plan and integration

1. Inspect the existing FastAPI services, session security, SQLite schema, React dashboard and tests.
2. Add an isolated voice router and additive `voice_profiles`/`voice_calls` tables. Preserve existing phase endpoints, authentication and data.
3. Add an authenticated enrollment and monitoring panel, plus a typed transcript simulator.
4. Test the signed provider flow, routing, retries, isolation and existing phases; build the frontend.
5. Configure a provider separately and perform genuine phone acceptance tests.

The implementation uses Twilio Programmable Voice for telephone connectivity, Hindi speech recognition and Hindi text-to-speech. A basic handset needs no application or internet connection. Twilio sends the recognized text to FastAPI; the frontend only displays authorized call history. Intent routing is deterministic Hindi/English keyword routing with keypad fallback, rather than an LLM. Crop advice still uses the existing trained model.

Flow: handset → Twilio number → signed HTTPS webhook → PIN → Hindi speech/DTMF → existing service → Hindi TwiML response. React polls private call history every five seconds.

## Local use without provider credentials

Start the existing app with `run-local.cmd`. Sign in and open **AI Voice Helpline** below the farm support panels. Enable the helpline using a six-digit PIN and transcript consent. This PIN is separate from the login OTP. The phone number is the account's registered phone, not an arbitrary number entered in the browser.

Select **Start simulation**, then type Hindi, English, or keypad digits. This exercises backend routing and transcripts, but **does not make calls or test speech recognition, audio quality, TTS, or the telephone network**. The browser session replaces PIN entry only for its own simulations.

- Main menu: 1 crop recommendation; 2 irrigation; 3 mandi prices; 9 repeat; 0 end.
- Crop advice: without an optional saved API profile, seven questions collect N, P, K, temperature (°C), humidity (%), pH, rainfall (mm). Values validate against the existing `CropInput`, then the model enforces its training ranges. Speak digits or use the keypad; `*` means decimal point and `#` submits. During numeric questions, 0 and 9 are numbers. Hindi digit characters and digit-based decimals are supported; Hindi spelled-out number words are not parsed. Use DTMF if the recognizer returns words.
- NPK must match the existing dataset-relative model units; no conversion from kg/ha, ppm, or mg/kg is invented. Rainfall period remains unspecified in the existing dataset. Do not guess unknown measurements. End the call if the required measurements are unavailable.
- Irrigation: save measured inputs in the dashboard first (maize/wheat/tomato, sowing date, area, coordinates, root depth, field capacity, wilting point, current depletion). Current water measurements must be saved on the same India-calendar date as the call. The existing Open-Meteo/weather and irrigation calculation services provide the response. Missing water measurements produce no precise quantity. These measurements are not inferred from photos. Updating inputs requires setting the PIN again and revokes existing active calls.
- Mandi: asks for wheat/rice/maize/tomato by voice or digits 1–4. It uses the saved farm state/district, returns one latest local observation with variety, date, INR/quintal and a stale-data warning. No matching official record means no quoted price. Use the existing import/sync workflow to populate official observations. No government data is seeded by this module.

Optional saved `crop` values can be supplied to `PUT /api/voice/profile` using the existing `CropInput` schema; the dashboard deliberately collects crop measurements during each call. Saving via the dashboard replaces any optional crop profile. Irrigation inputs are visible in the saved account profile and may be reloaded by checking the irrigation option.

## Configure real inbound calling

Obtain a Twilio account and a voice-capable number that can receive calls from the intended callers. Number availability, India routing/regulatory eligibility, trial restrictions, provider billing, and Hindi recognition availability must be verified with the provider for your account. No number was purchased and no credentials were configured during implementation.

Add these **server-only** values to `backend/.env` (never `VITE_` variables):

```dotenv
VOICE_ENABLED=true
VOICE_PUBLIC_URL=https://your-public-backend.example
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=your-account-auth-token
TWILIO_PHONE_NUMBER=+your-provider-number
```

`VOICE_PUBLIC_URL` must be the exact public HTTPS origin, without a path, query, fragment or trailing slash. Restart FastAPI after changing configuration. The token must be the account Auth Token used to sign incoming Twilio requests, not an API-key secret.

Expose the existing FastAPI server over HTTPS through your deployment or development tunnel. Configure these Twilio number webhooks, both using **HTTP POST**:

| Purpose | Public URL |
| --- | --- |
| A call comes in | `https://your-public-backend.example/voice/twilio/incoming` |
| Call status changes | `https://your-public-backend.example/voice/twilio/status` |

Gather action URLs are generated automatically as `/voice/twilio/input?step=N`. Preserve their exact query strings. Do not put these routes behind browser-session authentication or change their URL paths at the proxy. Browser `/api` origin checks remain enabled; provider routes independently verify the Twilio signature against the configured public origin, full path, query and all form parameters, then verify AccountSid and destination number. Forwarded host headers do not determine signature validation.

The server uses TwiML `Gather` with `language="hi-IN"`, speech plus DTMF, and `Say` with `voice="Polly.Aditi"`. PIN entry accepts DTMF only. Speech timeout, silence, low confidence and ambiguous intent lead to retries or keypad fallback. No raw audio is downloaded or stored by the app. No outbound dialing endpoint is provided.

Relevant provider documentation:

- [Gather: speech, language, DTMF and callback behavior](https://www.twilio.com/docs/voice/twiml/gather)
- [Hindi text-to-speech voices](https://www.twilio.com/docs/voice/twiml/say/text-speech)
- [Webhook signature construction and validation](https://www.twilio.com/docs/usage/security)

## Endpoints and access

| Method | Route | Access / purpose |
| --- | --- | --- |
| GET | `/api/voice/config` | Session; readiness, enrollment, saved inputs; no secrets or PIN hashes |
| PUT | `/api/voice/profile` | Session + existing CSRF; PIN, consent, optional crop/irrigation inputs |
| DELETE | `/api/voice/profile` | Session + CSRF; disables helpline and deletes account call history |
| GET | `/api/voice/calls` | Session; latest 30 calls owned by that account |
| POST | `/api/voice/simulate` | Session + CSRF; own-account simulation only |
| POST | `/voice/twilio/incoming` | Valid provider signature; starts a registered caller's PIN flow |
| POST | `/voice/twilio/input?step=N` | Signature + matching caller/call; idempotent ordered callback |
| POST | `/voice/twilio/status` | Signature; monotonic terminal-status updates |

Enrollment example body (do not use this illustrative PIN in deployment):

```json
{"pin":"654321","consent":true,"crop":null,"irrigation":null}
```

## Security and operating limits

- PINs use salted scrypt, are never stored in transcripts, and are not returned. Caller ID alone cannot unlock farm-based advice. Three failed inputs end a call; five failed PIN attempts across calls lock access for 15 minutes. Ten new provider calls per account per 15 minutes are allowed.
- Call state and transcript history persist in SQLite across restarts. Callback step responses are cached to avoid duplicate processing. Calls expire after 15 minutes and have at most 20 processed inputs. Provider terminal-status callbacks close active calls; without a callback, the dashboard can show an expired call as active until it is processed again.
- Use **one Uvicorn worker / server process**, matching this prototype's process-local locks and rate limits. Multi-process concurrency and durable queues require further work. The SQLite lock serializes state transitions inside this process. Weather fetches happen outside the lock; callbacks may wait up to the existing weather-service timeout, so measure provider latency during acceptance tests.
- Call history belongs to the farmer account; this is not a global operator console. No administrator roles were added. Unknown callers receive enrollment instructions without private advice. Consent is announced before PIN entry. Twilio may retain speech/DTMF request logs according to its own settings and terms; configure provider retention/access separately. Raw audio recording is not enabled by this application.
- Transcripts remain until the user deletes enrollment/history. The monitor retrieves the latest 30 calls; it is not an automatic deletion policy. Establish an appropriate retention policy before production.
- The helpline reuses the existing crop/irrigation/mandi **service functions** rather than making browser-authenticated HTTP calls to itself. It does not alter farm records or add advice to the older phase history tables.
- Credential readiness is configuration detection only. `liveVerified` remains false; it is not a provider health check. Never equate the simulator, unit tests, or a configured badge with a working real call.

## Verification and real-call acceptance

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests
.\run-local.cmd test-frontend
.\run-local.cmd build
```

New backend tests cover signed callbacks, invalid configuration/signatures, destination/account checks, PIN lockout/redaction, ordered/repeated callbacks, numeric collection including zero, model routing, missing data, recorded mandi units/dates, irrigation calculation, silence limits, consent, expiry, revocation, deletion and owner isolation. React tests cover the explicit simulation state, API flow, missing measurements, deletion, transcripts and failures. Synthetic prices and stubbed model/weather responses exist only in isolated tests.

After configuration, test manually with a real handset: enrolled and unknown numbers; correct/wrong PIN; Hindi speech; all keypad menu choices; all seven crop measurements; decimal and zero values; silence/noisy speech; missing/unavailable model and weather; official mandi records and no-data responses; hangup/status callback; repeated callbacks; cross-account isolation; transcript consent/deletion. Verify latency, pronunciation, unit comprehension, provider charges and log retention. **These real-call checks remain pending.**
