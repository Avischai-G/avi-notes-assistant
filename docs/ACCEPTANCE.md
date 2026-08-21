# Acceptance pass — live system

Run on **2026-08-21** against commit **7e22867** ("Correct submission claims and enter Taskmaster"),
working tree clean. Every value below is the real observed output, not a restatement of intent.

| | |
|---|---|
| Project | `gen-lang-client-0256233370`, region `us-central1` |
| `coroner` | https://coroner-295057934762.us-central1.run.app — revision **coroner-00013-krq** (deployed by this pass) |
| `coroner-orchestrator` | https://coroner-orchestrator-295057934762.us-central1.run.app — revision `coroner-orchestrator-00003-qsd` (unchanged) |

**Result: all seven acceptance items pass.** Two non-blocking findings are recorded at the end —
one is a genuine numeric inconsistency between two code paths, the other is cosmetic.

---

## Job 1 — redeploy `coroner` from HEAD

### Why it was needed

The revision that was live (`coroner-00012-k7t`) predated the documentation pass. The served
`app.js` still carried the false privacy claim:

> Nothing that identifies your project reaches the model — paths, URLs and keys are replaced before
> the first call.

A byte diff of the live asset against `web/app.js` at HEAD showed exactly the three hunks from
commit 7e22867 missing: the fleet-report preamble, the `runs saved` → `cases grouped` label, and
the privacy paragraph.

### How it was deployed

```
gcloud run deploy coroner --source . --region us-central1
```

No configuration flags were passed, deliberately. Cloud Run inherits every unspecified setting from
the previous revision, so nothing could be dropped by omission, and neither shared secret ever had
to appear on a command line.

### Proof that nothing was lost

The service was fingerprinted before and after. Environment variables are recorded as
`name → sha256(value)[:12]` with length, so preservation is proven without exposing a value.

| Setting | Before (`coroner-00012-k7t`) | After (`coroner-00013-krq`) |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | `3b6a43011639` len 26 | identical |
| `GOOGLE_CLOUD_LOCATION` | `8001c2743965` len 6 | identical |
| `GOOGLE_GENAI_USE_VERTEXAI` | `b5bea41b6c62` len 4 | identical |
| `CORONER_STORE` | `23066caccb55` len 9 | identical |
| `CORONER_MODEL` | `855faba1d992` len 16 | identical |
| `CORONER_RESUME_WEBHOOK` | `0c4748eb0007` len 68 | identical |
| `CORONER_RESUME_SECRET` | `c891ec8e1d47` len 64 | identical |
| `CORONER_JUDGE_KEY` | `92892648378e` len 64 | identical |
| memory / cpu | 1Gi / 1 | identical |
| timeout | 900s | identical |
| max instances | `autoscaling.knative.dev/maxScale: 3` | identical |
| container concurrency | 80 | identical |
| service account | `295057934762-compute@developer.gserviceaccount.com` | identical |
| port | 8080 (`http1`) | identical |
| startup CPU boost | true | identical |
| ingress | all | identical |
| IAM | `roles/run.invoker` → `allUsers` | identical |

A full diff of the two fingerprints returns **only two lines**: the revision name and the image
digest (`sha256:42b2f5d1…` → `sha256:2cc83979…`). Every other setting is byte-identical.

### The corrected text is live

All three served static assets are now byte-identical to HEAD (`diff` returns nothing for
`/app.js`, `/`, `/app.css`). The old sentence returns **0 matches** in every served asset, and
0 matches across every tracked file in the repository.

### `coroner-orchestrator` — checked, not redeployed

It is **already current**, so it was deliberately left alone. Timestamps could not settle this
(the commits were amended, so their dates post-date the build), so it was checked by behaviour
instead: HEAD's `stub_orchestrator.index()` was rendered locally against the live `/queue` rows and
diffed against the live page. The result is **byte-identical**. The service is running HEAD's code.

---

## Job 2 — acceptance

### a) All four views load and render — PASS

Captured with headless Chrome 151 at 1500×1300, plus full-height passes to inspect below the fold.

| View | Result |
|---|---|
| `#/graveyard` | Renders. Stat bar, then all 7 cause groups and all 39 case cards. |
| `#/fleet` | Renders. Headline, 4 figures, all 6 prescriptions with run-id lists. |
| `#/autopsy` | Renders. Corrected privacy paragraph in full, drop zone, 6-stage pipeline. |
| case file (`#/case/858e25a7-…`) | Renders. Certificate, trace facts, hypotheses, 3 lenses, revival kit. |

Nothing visually broken: no overflowing text, no empty panels, no collapsed layout, no missing
figures, footer present on every view. The full-height graveyard confirms the 39 cards distribute
across the groups exactly as the aggregate reports them — 12 / 8 / 6 / 5 / 4 / 3 / 1.

Screenshots: `shots/{graveyard,fleet,autopsy,casefile,graveyard-tall,casefile-tall}.png` in the
acceptance workspace (outside this repo).

### b) Corrected privacy wording live, old sentence gone — PASS

Live on `#/autopsy`, rendered and legible in the screenshot:

> Before the first call, Coroner pattern-masks POSIX, Windows and UNC paths; HTTP(S) and schemeless
> domain/path URLs; email and IPv4 addresses; JWTs, PEM private-key blocks, database connection
> strings, AWS access-key IDs and labelled AWS secret keys, bearer tokens, common prefixed tokens
> and long hexadecimal keys. Ordinary prose—including names, company names, business facts, phone
> numbers and unrecognized secret formats—still goes to Vertex AI unchanged; remove it before
> uploading.

Old sentence occurrences, searched whitespace-normalised so the line break cannot hide it:
`/app.js` **0**, `/` (index.html) **0**, `/app.css` **0**. Those are the only static assets the
image serves.

### c) API endpoints — PASS

| Endpoint | Observed |
|---|---|
| `GET /api/cases` | HTTP 200, **39** cases. 36 marked `revivable`. |
| `GET /api/fleet` | HTTP 200. Aggregate + **6** prescriptions grouping 33 run ids (12/8/5/4/3/1), each with `effort`. `unknown_run_ids: 0`, `duplicate_run_ids: 0`. |
| `GET /api/health` | `{"ok":true,"model":"gemini-3.5-flash","judge_key_configured":true}` |

Headline served: *"92% of 39 runs stopped without reporting a failure; 74 planned steps were
abandoned."*

### d) Live numbers vs `python -m app.metrics` — PASS, with one documented divergence

`./.venv/bin/python -m app.metrics` for `data/cases`, item by item against what the interface
actually renders:

| Rendered | Live | `app.metrics` | |
|---|---|---|---|
| runs autopsied / runs | 39 | 39 | match |
| died without a word | 92% | 92.3077% (36/39) | match |
| steps planned | 147 | 147 | match |
| banked | 73 | 73 | match |
| steps abandoned | 74 | 74 | match |
| still revivable | 36 | 36 (`revivable`) | match |
| **work banked before death** | **19%** | **17.6945%** | **disagree** |

Every rendered number matches except one. The graveyard stat bar (`web/app.js:40`) renders
`aggregate.mean_progress` under the label *"work banked before death"* as **19%**, while
`app.metrics` prints **mean progress: 17.6945%**.

This is **not stale data and not a Firestore drift**. Both formulas were run over the same local
`data/cases`:

```
USER_ABORT cases: 6
metrics formula  (all 39 cases):        0.1769452769 = 17.6945%
fleet formula (excl USER_ABORT, 33):    0.1933753116 = 19.3375%
live /api/fleet mean_progress:          0.1933753116
```

The live value reproduces the fleet formula exactly, which confirms Firestore's case set and
`data/cases` are the same data. The two code paths simply define the mean differently:

- `app/fleet.py:62` — `if cause != "USER_ABORT": progress.append(...)` — averages over 33 runs.
- `app/metrics.py:91` — `progress.append(fraction)` unconditionally — averages over all 39.

Excluding deliberate user aborts from "work banked before death" is defensible, arguably more
honest than including them. The defect is that the two paths disagree silently and neither states
its denominator. See finding 1.

Also verified: `/api/fleet` recomputes its aggregate live from Firestore
(`fleet.finalize` calls `aggregate(cases)`), so these numbers are freshly derived, not read from
the cached `data/fleet.json`. Only the model's groupings come from the cache; the counts,
`deaths_prevented` and the headline are recomputed and validated in Python.

### e) Companion service anonymous access and auth — PASS

| Request | Observed |
|---|---|
| `GET /` | HTTP 200, page renders anonymously |
| `GET /queue` | HTTP 200, JSON, anonymously |
| `POST /resume` no secret | **HTTP 401** `{"detail":"valid resume shared secret required"}` |
| `POST /resume` wrong secret | **HTTP 401** `{"detail":"valid resume shared secret required"}` |

The wrong-secret case was tested in addition to the missing-secret case, to confirm the guard
compares the value rather than merely checking that a header is present.

### f) Handing a case back — PASS

Chose `858e25a7-e6cb-4506-b530-596d0294667c` ("Lighthouse Beacon Rotation Assembly Inspection",
`STALLED_ON_USER`, confidence 0.99) — `revivable: true`, and not already in the queue so that a new
arrival would be unambiguous.

`POST /api/case/858e25a7-…/resume` → HTTP 200:

```json
{"delivered": true, "status": 200,
 "detail": "{\"accepted\":true,\"queued\":\"858e25a7-…\",\"note\":\"a real orchestrator would now re-dispatch this run\"}",
 "endpoint": "https://coroner-orchestrator-295057934762.us-central1.run.app/resume"}
```

The companion's queue went from **3 → 4** entries. The new entry carries the full plan — title,
`cause_of_death: STALLED_ON_USER`, `confidence: 0.99`, `resume_at: af8dc75d`, and the restart
prompt — and it renders on the companion's page. The loop works end to end across both services.

> This left a real, permanent 4th row in the public demo queue. Remove it before submission if the
> queue was curated to three.

### g) Cloud Scheduler — PASS

`gcloud scheduler jobs describe coroner-sweep --location us-central1`:

```
state:           ENABLED
schedule:        */15 * * * *   (Etc/UTC)
uri:             https://coroner-295057934762.us-central1.run.app/api/sweep
httpMethod:      POST
attemptDeadline: 900s
lastAttemptTime: 2026-08-21T08:00:02.835526Z
status:          {}          ← no error recorded, i.e. the attempt succeeded
```

Observed at 08:03:11Z, so the last attempt was **3 minutes old**. Scheduler logs confirm a clean
cadence with no ERROR entries: 08:00:05, 08:00:04, 07:45:10, 07:45:10, 07:30:10 — all INFO.

The sweep's own record (`GET /api/sweep`, free) corroborates it:

```json
{"at": 1787299202.89 (2026-08-21T08:00:02Z), "watched": 39, "already_known": 39,
 "silent": 39, "autopsied": [], "handed_back": [], "errors": [], "skipped_terminal": 0}
```

`autopsied: []` — the scheduled sweep found nothing new and spent nothing.

---

## Spending

No billable model call was made. `POST /api/autopsy` was never called. `POST /api/fleet/recompute`
was never called. `POST /api/sweep` was **not called at all** — the read-only `GET /api/sweep`
already carried the evidence item (g) needed, so neither of the two permitted calls was used. The
only cost incurred was the one Cloud Build for the redeploy.

---

## Findings

**1. `mean_progress` is computed two different ways, and the UI shows the one the CLI does not.**
Non-blocking but real, and it is a number a judge can check.
`app/fleet.py:62` drops `USER_ABORT` runs from the mean; `app/metrics.py:91` keeps them. The
interface renders 19% under *"work banked before death"* while `python -m app.metrics` prints
17.6945% for the same corpus. Neither label states its denominator, so the two can never be
reconciled by a reader. Cheapest honest fix is to leave the arithmetic alone and label it — e.g.
*"work banked before death (excluding user aborts)"* — or to align `metrics.py` with the same
exclusion. Not changed here: the instruction for this pass was not to touch application code.

**2. Cosmetic: "1 steps planned".**
`app/findings.py:114` interpolates `f"{total} steps planned; …"` with no singular handling, so a
one-step run reads *"1 steps planned; banked 0 (0%)"* on the case-file view. Visible on the case
file used above. The very next bullet in the same list uses the `"1 step(s)"` convention, so this
is an inconsistency with the codebase's own style rather than a missing idea.

Nothing else was found. The four views render correctly, the corrected privacy wording is live and
the false claim is gone everywhere, all endpoints return the expected values, both services are
running HEAD's code, the resume loop works across services, and the scheduler is healthy.
