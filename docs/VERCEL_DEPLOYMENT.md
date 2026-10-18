# Vercel services deployment

The root vercel.json defines two independently built services:

| Name | Root | Framework | Public requests |
| --- | --- | --- | --- |
| backend | backend | FastAPI, entrypoint main:app | /api/* and /voice/* |
| frontend | frontend | Vite | All remaining paths |

These names and public routes require owner confirmation before publishing.
The /voice/* rewrite is needed for Twilio incoming, input, and status callbacks.
Services receive the original request path. FastAPI already defines /api/* and
/voice/*, so no prefix stripping or route renaming is needed.

## Bindings

There are no internal service-to-service calls. React runs in the browser and
uses same-origin /api requests; the frontend service serves static assets.
FastAPI calls external weather/market APIs and its own local Python modules.
No binding is declared because there is no server-side caller to consume one.
Do not expose an internal service URL through a VITE_ variable or use a binding
at build time. No BACKEND_ORIGIN variable or external-backend build script is
needed in this services configuration.

The Vite localhost proxy is only for standalone local development. In Vercel,
the top-level service rewrites route API and voice traffic. Use `vercel dev`
from the repository root to exercise both services; `vercel dev -L` runs without
cloud authentication. Set the required backend environment variables first.

## Environment and unresolved runtime requirements

Local .env files and stored user data are excluded from deployment. Configure
server secrets in Vercel environment settings; never prefix secrets with VITE_.
Set APP_ORIGIN to the exact public frontend HTTPS origin for CSRF checks.
Set VOICE_PUBLIC_URL to that same shared public origin, and configure Twilio
POST webhooks at /voice/twilio/incoming and /voice/twilio/status.
See backend/.env.example and VOICE_HELPLINE.md for the remaining variables.

The service configuration is ready for review, but the full app is not yet
production-ready on Vercel:

- Turso and private Vercel Blob adapters are implemented. Provision a Turso
  database and connect a PRIVATE Blob store before deploying. Set
  TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, and PHOTO_STORAGE=vercel-blob. Vercel
  supplies Blob credentials through the project connection. Startup refuses
  local ephemeral storage when VERCEL=1. Existing local records and photos are
  not automatically migrated. Hosted integrations still require live testing.
- Production SMS uses Twilio Verify. Create a six-digit SMS Verify service,
  set TWILIO_VERIFY_SERVICE_SID (VA...), TWILIO_ACCOUNT_SID, and TWILIO_AUTH_TOKEN,
  and set APP_ENV=production and DEMO_AUTH=false. No SMS is sent during tests.
  Trial restrictions and provider charges still apply. OTP approval must come
  from Twilio; a local hash cannot approve a production login.
- The original call workflow uses process-local locks. Its concurrency and
  provider rate limits require review before serving multiple Vercel instances.
  Remote database persistence alone does not provide distributed locking.
- Trained model artifacts are ignored by Git and excluded from this upload.
  Core requirements omit TensorFlow, PyTorch, and other ML dependencies.
  Model endpoints will remain unavailable until model hosting, dependencies,
  and artifact delivery are addressed within the hosting limits.

This file does not claim a successful live deployment. After resolving these
requirements, test login, farm save/reload, photo upload, model availability,
and a real Twilio call on the deployed domain.
