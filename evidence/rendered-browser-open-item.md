# Merged rendered-browser QA — UNVERIFIED

## Exact attempted command

```sh
UI_BASE_URL=http://127.0.0.1:8764 npm run test:ui
```

The offline FastAPI service had completed startup. Playwright failed before page
context creation; no app navigation or rendered assertion ran.

## What was resolved outside this run

The initial environment had a browser/driver version mismatch. Avi installed the
matching builds (`webkit-2336`, Chromium `1234`, and headless-shell `1234`) and
independently proved both matching Chromium and WebKit could launch and read a
probe DOM outside this run.

## Final unchanged run in this sandbox

The command above was rerun unchanged after that repair. Playwright launched
system Google Chrome as PID `92520`, but the browser closed before context
creation. The observed terminal facts were:

```text
browserType.launch: Target page, context or browser has been closed
exception while trying to kill process: Error: kill EPERM
process did exit: exitCode=null, signal=SIGABRT
```

The complete launch call log is preserved in `evidence/browser/report.json`.

## Claim boundary

Card 2's and Card 4's rendered checks passed individually earlier in the project.
Separately, Avi/Main Orchestrator executed a temporary diagnostic copy of the
merged suite outside this sandbox. Its eight task/learning matrix checks passed
and it isolated three harness defects: an already-focused composer, a wait for a
hidden element to become visible, and expected raw-log 404s poisoning final
console diagnostics. That execution was not observed by this executor and did
not run the final corrected repository file. Its supplied JSON and screenshots
are preserved in `evidence/browser-orchestrator/`.

Merged desktop/mobile, dark/light, keyboard, accessibility, console, and network
QA is therefore `UNVERIFIED` from this executor's position—not claimed as a
first-party pass.

## Exact next verification

Run the corrected repository's unchanged `npm run test:ui` outside this managed
sandbox. No launch option, browser engine, retry, or fallback was attempted after
the final `SIGABRT` result.
