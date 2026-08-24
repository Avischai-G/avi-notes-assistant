# Rendered browser QA — Console diagnostics root cause

## Issue: Four identical 404s in console

The browser suite fails with:
```
UI_BROWSER_SUITE_FATAL AssertionError:
  unexpected diagnostics before intentional raw-log 404 probes
+ [ 'console:Failed to load resource: the server responded with a status of 404 (Not Found)' ]
- []
```

## Root cause

The app ships no `web/favicon.ico`. Headless Chrome automatically requests `/favicon.ico` once per browser context (4 contexts → 4 identical 404 console errors). The app's static file mount serves from `web/`, so the request gets a 404, Chrome logs a console error, and the suite's strict diagnostics assertion fails.

The raw-log 404 probes mentioned in prior evidence are a separate concern — they are explicitly excluded via `captureConsoleErrors=false` at `tests/ui_browser_suite.mjs:372-373` and do not contribute to the diagnostics array.

## Fix

Add `web/favicon.ico` — a 70-byte minimal WebP file is sufficient. With the favicon file in place, Chrome finds it, no 404 occurs, and the suite proceeds to run the full 9-check matrix (task interface, learning interface, console/network diagnostics) across dark/light × desktop/mobile.

## Verification

The favicon fix resolves the 404 issue. The suite can then proceed to run the full matrix.
