# Acceptance pass — live Coroner system

Run on **2026-08-21** against commit **`ffb1736`** with a clean worktree. Every
value below is an observed result from this pass.

| Surface | Observed live state |
|---|---|
| Project / region | `gen-lang-client-0256233370` / `us-central1` |
| `coroner` | `https://coroner-295057934762.us-central1.run.app`, revision **`coroner-00015-trh`**, 100% traffic |
| `coroner-orchestrator` | `https://coroner-orchestrator-295057934762.us-central1.run.app`, revision `coroner-orchestrator-00003-qsd`, unchanged |
| Model | `gemini-3.5-flash` on Vertex AI, location `global` |

**Result: all nine pre-deploy checks and all seven live acceptance items pass.**
No product defect was found. The only non-failing warning was a local
`StarletteDeprecationWarning` from FastAPI's test client; it did not affect a check or the live
service.

## 1. Pre-deploy gate — nine checks passed

All checks ran from the clone with
`/Users/avischaigrau/Developer/coroner/.venv/bin/python`. Nothing was weakened or
changed to make a check pass.

| Check | Exit | Observed result |
|---|---:|---|
| `test_corpus.py` | 0 | 39 traces; 39/39 attributed; 0 undetermined; 36/39 silent = 92%; mean progress 18.0% over rule-prior non-user-aborts |
| `test_published.py` | 0 | 40 private traces, 39 published; no banned strings or six-word phrasing carried over |
| `test_inputs.py` | 0 | 29 malformed shapes rejected cleanly; HTTP never returned 500 |
| `test_stream.py` | 0 | six stages in order; three investigators overlap; case delivered; model failure becomes an SSE error |
| `python -m app.redact` | 0 | nothing leaked; placeholders stable |
| `python -m app.watch` | 0 | stale non-terminal runs swept; fresh and finished runs left alone |
| `python -m app.limits` | 0 | per-caller and per-instance ceilings hold and refill |
| `python -m app.resume` | 0 | valid delivery works and all failure paths report failure |
| `python -m app.metrics` | 0 | verdict definitions pass; public metrics printed successfully |

The final metrics command against `data/cases` reported 39 cases, 93 hypotheses,
53/93 killed by majority, 13/93 non-unanimous, 26/279 pairwise disagreements,
9/39 cases with a non-unanimous hypothesis, 8/39 certified/prior disagreements,
36/39 silent stops, 19.3375% mean progress over non-user-aborts, and 147/73/74
planned/banked/abandoned steps.

## 2. Deployment and preservation proof

The deployment command was exactly:

```text
gcloud run deploy coroner --source . --region us-central1
```

No service configuration flags were passed. The CLI configuration directory was relocated into
the acceptance workspace because the managed sandbox cannot write the default home directory;
that changes only where `gcloud` reads credentials and does not change the deployment request.

Cloud Build completed and Cloud Run routed 100% of traffic to `coroner-00015-trh`.
The image changed from
`sha256:1bd70fda440927f496789cff032668920950396ae0324f7897dbe5c03105ec31`
to
`sha256:7257a444025c5ee92239ae402327cb6dd303759deeaeae243768cf4089e34b2c`.

### Eight environment variables survived

Each value is recorded only as `sha256(value)[:12]` and length. No value was printed or put on a
command line.

| Variable | Before `00014-mzp` | After `00015-trh` |
|---|---|---|
| `CORONER_JUDGE_KEY` | `92892648378e`, len 64 | identical |
| `CORONER_MODEL` | `855faba1d992`, len 16 | identical |
| `CORONER_RESUME_SECRET` | `c891ec8e1d47`, len 64 | identical |
| `CORONER_RESUME_WEBHOOK` | `0c4748eb0007`, len 68 | identical |
| `CORONER_STORE` | `23066caccb55`, len 9 | identical |
| `GOOGLE_CLOUD_LOCATION` | `8001c2743965`, len 6 | identical |
| `GOOGLE_CLOUD_PROJECT` | `3b6a43011639`, len 26 | identical |
| `GOOGLE_GENAI_USE_VERTEXAI` | `b5bea41b6c62`, len 4 | identical |

### Requested service settings survived

| Setting | Before | After |
|---|---|---|
| Memory / CPU | `1Gi` / `1` | identical |
| Timeout | 900 seconds | identical |
| Max instances | 3 | identical |
| Container concurrency | 80 | identical |
| Service account | `295057934762-compute@developer.gserviceaccount.com` | identical |
| Ingress | `all` | identical |
| Invoker IAM | `roles/run.invoker` → `allUsers` | identical |

### The new container payload is present

- `GET /api/health` returned 200 with `ok: true`, model `gemini-3.5-flash`, and
  `judge_key_configured: true`.
- `GET /api/agents` returned six agents. A recursive diff of its six `markdown` strings against
  `prompts/` returned **exit 0**. Import would fail if the prompt directory were absent.
- `GET /api/samples` returned three entries. Each allowlisted `GET /api/samples/{run_id}` returned
  200 with the matching run ID; an unknown ID returned 404. Those endpoints read the shipped
  `data/demo-traces` files at request time.
- A recursive diff of the live `/`, `/app.js`, `/app.css`, and `/copy.js` payloads against `web/`
  returned **exit 0**. The rebuilt interface at HEAD is what the revision serves.

### Companion service was checked, not redeployed

`stub_orchestrator.py` and `requirements.txt` have no diff from `c645d39` to HEAD. The only shared
Dockerfile changes add prompt and demo-trace files required by `coroner`; they do not change the
stub's runtime. More decisively, the live companion page was rendered locally from HEAD against
the live queue before and after the hand-back. Both byte diffs were clean:

| State | Queue rows | Bytes | SHA-256 | Live vs HEAD renderer |
|---|---:|---:|---|---|
| Before hand-back | 4 | 3,537 | `350edd5754925270a687ca3d2bad96cb26cd58f89b7aee461ea2fb6cabe6a5a3` | identical |
| After hand-back | 5 | 4,296 | `3911e7578090dbaf7d5690a42167cc115e8535e063292391e1c5ea0f4c450a09` | identical |

The already-current revision `coroner-orchestrator-00003-qsd` was therefore deliberately left
untouched.

## 3. Live acceptance

### a. Every view loads and renders — PASS

Chrome for Testing was driven at a **1280×900 viewport**. The in-app browser-control runtime was
not exposed in this managed session, and ordinary sandboxed Chromium processes were denied macOS
Mach-port registration. The installed Chrome-for-Testing binary worked in single-process mode;
this is a browser-harness constraint, not a service defect.

For every view, the page title was `Coroner — post-mortems for dead agent runs`, meaningful body
content rendered, no framework overlay appeared, `scrollWidth == clientWidth == 1280`, and the
rendered body contained no literal `undefined`, `null`, or `NaN`. The companion queue had its own
expected title. All screenshots below were opened and inspected manually after capture.

Evidence lives in `../acceptance-evidence` from the repository root.

| Screenshot | Pixels | Bytes | SHA-256 prefix | Observation |
|---|---:|---:|---|---|
| `01-autopsy-front.png` | 1280×1347 | 180,333 | `a341b8a0fae9` | Front door, three samples, idle six-stage terminal, aggregate figures |
| `02-live-three-running.png` | 1280×1509 | 229,949 | `17810124398d` | Mid-run; UI says “3 agents running at once”; all three investigator rows active |
| `03-live-complete.png` | 1280×2736 | 530,597 | `717aa8407aa9` | All six stage results, overturned banner, finished payoff |
| `04-live-case.png` | 1280×2571 | 476,364 | `bd33e6032481` | Finished live case file and revival kit |
| `05-agents.png` | 1280×4228 | 535,669 | `8357c6f43fc7` | Six prompt cards, complete markdown visible |
| `06-taskmaster.png` | 1280×3461 | 599,849 | `5af56dd1f3f2` | Taskmaster category and live fleet figures |
| `07-partner.png` | 1280×2211 | 338,483 | `1dec686d6ff8` | Collaborative Partner non-fit page |
| `08-enterprise.png` | 1280×2733 | 477,500 | `d33029a7894a` | Fortified Enterprise Fleet non-fit page |
| `09-graveyard.png` | 1280×2290 | 273,755 | `6cc0fbcf35f4` | Stripped Graveyard, all 39 cards across seven rendered groups |
| `10-fleet.png` | 1280×1256 | 214,793 | `73675698c030` | Stripped Fleet report, six prescriptions |
| `11-orchestrator-queue.png` | 1280×1184 | 226,462 | `d2ddd9fcb82a` | Five-row companion queue after the real hand-back |

Nothing was overflowing, empty, collapsed, clipped, or horizontally scrollable. Browser console
errors were limited to the deliberately requested unknown sample (404) and the two deliberately
unauthorized resume calls (401); there were no application errors or warnings during ordinary
view rendering.

### b. One sample autopsy, end to end — PASS

Sample 2 was clicked once from the live front page:

- Label: “All six steps waiting on a human”
- Run: `02266df1-6d2e-42be-8239-c243bd0896de`
- Model-backed calls: exactly six — triage, three investigators, certification, revival
- Terminal state: `complete`; six done rows, zero failed rows
- Finished case: **Allotment Watering Roster System**
- Recorded prior: `WORKER_TERMINATED`
- Certified cause: `STALLED_ON_USER`, confidence **0.9**
- Overturned banner: 3/3 investigators refuted the prior and 3/3 retained the certified cause
- Storage: `/api/cases` was 39 before and 39 after, confirming the live case was not stored

The browser recorded these stage transitions in `performance.now()` milliseconds:

| Event | Observed time |
|---|---:|
| Triage start / done | 3,287.0 / 13,193.2 |
| All three investigators start | **13,193.2** |
| First investigator done | 23,495.9 |
| Remaining investigators done | 26,077.5 and 27,345.6 |
| Certification start / done | 27,345.6 / 31,561.3 |
| Revival start / done | 31,561.4 / 37,961.4 |

Thus all three investigator starts preceded every investigator completion, with more than ten
seconds of visible overlap. The terminal displayed 34.9 seconds at completion.

The run was made **once**. It was not repeated after completion.

### c. The prompts shown are the prompts that ran — PASS

`app/autopsy.py:63-77` reads each file once at import. `_agent` uses that loaded object's
instruction at `app/autopsy.py:190-210`; `agent_cards` returns the same loaded object's markdown at
`app/autopsy.py:311-314`; and `GET /api/agents` returns those cards at `server.py:154-158`.

The live API returned six agents, all on `gemini-3.5-flash`. Its markdown was written to an
evidence directory and compared with `diff -ru prompts live-prompts`; the command returned **0**.

| Agent | Bytes | SHA-256 |
|---|---:|---|
| `triage` | 643 | `bc0fca724f14a4f389bc83a849291d4d44f9d28b517d9d4e625f5cad3040ab62` |
| `investigator_sequence` | 846 | `b5cfa5080aa0ee78f2f0a413636f923ebfdd694ed8d411574192b32a47bff618` |
| `investigator_counterfactual` | 836 | `d5803bf5d260131d051903296a1c29e45bc51862541f52894512838354af0dd1` |
| `investigator_alternative` | 919 | `94fbd6f7699c95e3acbf82cbe63f8ee904b11d8116ce9631d6dfeca1f39f7bf3` |
| `certify` | 1,110 | `60cd72479cbff8ad33aaf5b0418c73f3cd4baaeed652d78c5085d0dd9787e9c1` |
| `revive` | 1,172 | `95aeb54c06c49e4038df168e176d80278b1fcedecf07306665c40e82058db285` |

### d. Rendered numbers reconcile — PASS

The home and Graveyard read `/api/fleet` plus `/api/cases` (`web/app.js:99-118` and
`web/app.js:327-347`). The Taskmaster figures read `/api/fleet` (`web/app.js:556-568`). The
endpoint recomputes its aggregate from the live Firestore cases through `fleet.finalize`
(`server.py:175-182` and `app/fleet.py:46-76`); only the six prescription wordings come from the
shipped cache. `app.metrics.py:82-111` independently measures `data/cases`. Both progress code
paths now exclude `USER_ABORT` with the same denominator.

| Figure | Live API / rendered source | `python -m app.metrics data/cases` | Result |
|---|---:|---:|---|
| Cases | 39 | 39 | match |
| Silent stops | 36 / 39 = 92.307692% (renders 92%) | 36 / 39 = 92.3077% | match |
| Mean progress, excluding user aborts | 19.337531% | 19.3375% | match |
| Steps planned | 147 | 147 | match |
| Steps banked | 73 | 73 | match |
| Steps abandoned | 74 | 74 | match |
| Certified cause differs from prior | 8 | 8 | match |
| Still revivable | 36 | 36 counted from the same local cases | match |
| Ranked prescriptions | 6 | cached prescription count, validated by Python | match |

There are **no numeric disagreements**. The hardcoded banner prose “8 of the 39 autopsied runs
came out this way” is still true: live `/api/cases` contained exactly 8 `overruled: true` rows out
of 39, and `app.metrics` independently measured 8 certified/prior disagreements out of 39.

### e. Auth and rate limits hold — PASS

Companion service, anonymously:

| Request | Observed |
|---|---:|
| `GET /` | 200 |
| `GET /queue` | 200 |
| `POST /resume`, no secret | **401** |
| `POST /resume`, wrong secret | **401** |

Coroner's rate-limiter proof used malformed JSON (`"{"`) so every allowed request stopped at the
parser before a model call:

- After the one real sample had consumed one caller token, four malformed requests returned 400.
- The fifth malformed request was refused with **429**, `Retry-After: 560`.
- A wrong judge key remained **429**, `Retry-After: 559`.
- The real judge key bypassed the exhausted bucket and reached the parser, returning **400**.

The key was read into process memory from the live service description; it was never printed,
logged, written to evidence, or placed on a command line. The limiter proof made **zero** model
calls. The test caller's per-caller bucket refills automatically; it did not affect other callers.

### f. The hand-back loop closes — PASS

The stored case `02266df1-6d2e-42be-8239-c243bd0896de` was revivable and not yet queued. The
case-file button made one real `POST /api/case/{run_id}/resume`:

- UI response: “Delivered — the orchestrator accepted it (HTTP 200).”
- Companion response: `accepted: true`, queued the same run ID.
- Queue count: **4 → 5**.
- The new row carried a non-empty restart prompt and rendered as the first card on the companion
  page; `11-orchestrator-queue.png` is the visual proof.

This queue row is persistent by design and was not deleted after acceptance.

### g. Cloud Scheduler is healthy — PASS

Observed at `2026-08-21T16:37:23Z`:

```text
state: ENABLED
schedule: */15 * * * *
timeZone: Etc/UTC
attemptDeadline: 900s
httpMethod: POST
uri: https://coroner-295057934762.us-central1.run.app/api/sweep
lastAttemptTime: 2026-08-21T16:30:05.003331Z
status: {}
```

An empty scheduler `status` means the last attempt recorded no error. The free
`GET /api/sweep` returned:

```json
{"already_known":39,"at":1787329805.0501409,"autopsied":[],"errors":[],"handed_back":[],"silent":39,"skipped_terminal":0,"watched":39}
```

That service timestamp is `2026-08-21T16:30:05.050141Z`, only **0.046810 seconds** after the
scheduler's recorded attempt. `autopsied`, `handed_back`, and `errors` were all empty, so the sweep
found nothing new and spent nothing.

## Spend and persistent state

- One Cloud Build for the required deployment.
- One sample autopsy: exactly six `gemini-3.5-flash` calls.
- Zero calls to `POST /api/fleet/recompute`.
- Zero manual calls to `POST /api/sweep`; only the free GET was used.
- Zero model calls from the limiter proof.
- One requested hand-back, leaving the public demo queue at five rows.

The live rebuilt service passes the requested acceptance scope without a product defect being
smoothed over.
