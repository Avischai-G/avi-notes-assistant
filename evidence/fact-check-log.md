# Fact-check log

| Claim | Status | Evidence / resolution condition |
|---|---|---|
| The full merged offline suite passes. | PASS | `69 passed, 1 skipped` both in the integration tree and from clean checkout `5a05d51`; the skip is the credential-gated isolation regression. |
| Model, location, and framework drift each fail eligibility. | PASS | `test_foundation_complete.py` mutates all three independently and requires `RuntimeError`. |
| `test_chat_foundation.py` is a real, passing test. | PASS | It now instantiates the agent correctly and calls the registered FastAPI health route. |
| Card 3 boundary files are byte-identical. | PASS | Six supplied boundary artifacts, including the five executable/test files Card 9 tracked, matched by `cmp` and SHA-256; see `card3-hashes.md`. |
| Notion isolation still returns exactly one configured data source. | UNVERIFIED this run | Run the unchanged live regression after explicit live-test approval. |
| Desktop/mobile dark/light UI and keyboard matrix pass on the merged bundle. | UNVERIFIED | After Avi installed matching Playwright browsers and proved Chromium/WebKit outside this run, unchanged `npm run test:ui` still failed before context creation here: system Chrome exited `SIGABRT` and cleanup returned `kill EPERM`. Exact output is in `evidence/browser/report.json`. Earlier individual Card 2/Card 4 rendered checks do not prove the merged bundle. Avi will run the prepared suite outside this sandbox. |
| Raw learning log has no HTTP route. | PASS offline / live pending | Offline route tests require 404; repeat over the authenticated live service after approval. This does not substitute for the unverified rendered-browser check. |
| The approved live story passes and marker rows are archived. | UNVERIFIED | Requires Avi's explicit yes and direct observation. |
| Chat, automation histories, learning, and knowledge survive reload. | UNVERIFIED | Requires authenticated Firestore/knowledge live run. |
| Clean-checkout setup and offline verification pass. | PASS | `setup.sh` completed with Python 3.12.12, npm reported zero vulnerabilities, `69 passed, 1 skipped`, compilation/JS/diff checks passed, tracked files stayed clean, and all six Card 3 comparisons matched at `5a05d51`. |
| No secret appears in worktree or reachable git history. | PASS post-integration / final rerun pending | Scanner inspected 65 repository/local-data files, 2,889,584 reachable-history bytes, five exact sensitive values, and four generic credential patterns. Generated dependency/cache directories are explicitly excluded. Rerun after the verification commit. |
| Release candidate is locally tagged. | PENDING | Tag only after all approved acceptance checks pass. |
| Any cloud deployment, remote push, publication, recording, or submission occurred. | NO | Prohibited and not attempted. |
