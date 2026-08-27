# Security review — 2026-08-25

Scope: the full application (backend, frontend, deployment, git history),
with emphasis on API-key exposure ahead of external evaluation.

## How credentials are held

| Credential | Where it lives | What can see it |
|---|---|---|
| Owner's Gemini API key | GCP Secret Manager (`avi-notes-gemini-key`) → Cloud Run env `GEMINI_DEFAULT_API_KEY` | The server process only. Never in git, the image, logs, or any API response. |
| A visitor's Gemini API key | That browser's `localStorage` only | Only the device it was typed on. Sent per request (`X-Gemini-Key` header / WebSocket init frame — never URLs, so never in request logs). Selects an in-memory per-key agent; nothing is persisted server-side. |
| Notion token + database id | Secret Manager → env | Passed only into the MCP child's environment; stderr flows through a redacting pipe; error strings are scrubbed before they can propagate. Never in argv or prompts. |
| Vertex (fallback) | Cloud Run service identity | No key material at all. |

The Settings key field is masked: `type=password` (dots only) with copy/cut
blocked. It shows the device's own stored key back to the device that stored
it — the key lives in that browser's localStorage and never reaches any other
party — and no server endpoint echoes a key or even whether one exists. A key
stored by an older build in Firestore is scrubbed at boot, and the settings
API silently ignores any `gemini_api_key` an old client sends.

## Update — 2026-08-28

Three stored items were added since the review above; none widens what a
browser can read:

| Item | Where it lives | Notes |
|---|---|---|
| Notion secret pasted in Settings | Firestore settings document | Write-only: validated with one board read, never echoed to any browser (the field shows stand-in dots). Clearing it falls back to the Secret Manager secret. |
| Web Push VAPID private key | Firestore settings document | Generated once by the app; signs outgoing push messages only. The public half is served at `/api/push/key`. |
| Push subscriptions | Firestore settings document | Browser push endpoints plus their public encryption keys — capped at five, pruned when a push endpoint reports the subscription gone. |

## Verified clean

- **Secret scan** over the working tree and the *entire git history*
  (`AIza…`, `ntn_…`, `secret_…`, private-key blocks): no real secrets. The
  only two pattern hits are a synthetic fixture inside the secret-scanner's
  own tests.
- **XSS**: every dynamic HTML sink escapes first (`esc()` before the markdown
  transforms, chips, drawer rows); automation ids are server-sanitized to
  `[a-z0-9-]`.
- **Log hygiene**: keys never appear in URLs (headers/WS frames by design);
  the gated `LIVE_DEBUG` probes print event shapes, never payloads.
- **CORS**: no CORS middleware, so browsers enforce same-origin; the JSON
  POST endpoints require a preflight that cross-origin pages cannot pass.
- **Attachments**: server-side MIME allowlist (image/PDF), 20 MB cap,
  validated base64.
- **Service worker**: never caches `/api/*`; network-first everywhere else.
- **Firestore**: reached only by the server's service account; no client SDK.

## Open findings

1. **HIGH — No authentication.** Anyone with the URL can chat (spending the
   server credential), read the board through the agent, run automations, and
   edit the system prompt. Accepted for the evaluation hand-off (evaluators
   need frictionless access); before any real use, put Cloud Run behind IAP
   or add a shared access token checked on every route.
2. **MEDIUM — Prompt injection.** Board rows, page bodies, and web-search
   results feed the model; hostile content could steer it. Blast radius is
   bounded: write tools reach exactly one Notion database, and the voice
   agent has no write tools at all.
3. **LOW — Container runs as root** (python-slim default). Cloud Run's
   sandbox mitigates; a `USER` directive would tighten it.
4. **NOTE — localStorage keys** are readable by script on this origin. The
   app ships no third-party script; a CSP header would harden this further.
