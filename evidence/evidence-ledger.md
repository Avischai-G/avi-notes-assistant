# Evidence ledger

All times are `Asia/Jerusalem` calendar date 2026-08-23 unless stated otherwise.
Raw secrets and local credential contents are never recorded here.

| Action | Input / scope | Observed result | Evidence |
|---|---|---|---|
| Created integration clone | Read-only source `~/Developer/coroner`; removed local origin | Workspace-local `release-candidate`, branch `main`, inherited `pre-rebuild` tag, no remote | `git status`, `git remote -v` |
| Read upstream card evidence | Cards 2, 3, 4, 5, 9 and shared build-plan/handoffs | Card 9 selected as behavioral base; Card 3 boundary retained; Card 2 UI and Card 4/5 modules joined | Agentonomy held-run evidence and shared handoffs |
| Removed obsolete surfaces | Legacy product modules, data, prompts, pages, routes, and submission copy | Removed from final tree; history and `pre-rebuild` remain the archive | Final git diff |
| Repaired eligibility evidence | Model, location, framework mutations | Each mutation now must raise `RuntimeError`; false printed guarantee removed | `test_foundation_complete.py` |
| Repaired chat foundation | Broken class-level config call and mock-only health assertion | Actual agent instance and actual FastAPI route are exercised | `test_chat_foundation.py` |
| Local setup | Repository `setup.sh` with workspace-installed Python 3.12.12 | Initial macOS Python 3.9 selection failed the ADK requirement; setup now fails early below Python 3.12 and completed with Python 3.12.12; npm audit found zero vulnerabilities | `setup.sh`, terminal output |
| Merged-suite test | Python suite plus JavaScript syntax and diff whitespace | `69 passed, 1 skipped`; Python compiled; all JavaScript parsed; `git diff --check` passed | pytest, compileall, `node --check`, `git diff --check` output |
| Added live-row containment | Marker-scoped wrapper plus synthetic reset | Offline guard tests prove unowned rows hidden and mutation rejected | `tests/test_marker_scoped_store.py` |
| Compared Card 3 boundary | Six source/destination pairs | Every pair byte-identical; SHA-256 values recorded separately | `evidence/card3-hashes.md` |
| Secret scan before commit | Worktree (including installed dependencies), reachable patches, exact local sensitive values, generic credential shapes | PASS: 2,320 files; 1,542,936 history bytes; 5 exact values; 4 generic patterns | `tools/secret_scan.py` stdout |
| Attempted merged rendered QA | First `UI_BASE_URL=http://127.0.0.1:8764 npm run test:ui`, then—after matching browsers were installed—unchanged `npm run test:ui` | `UNVERIFIED`: no browser context in this sandbox. The final unchanged run launched system Chrome, then it exited `SIGABRT`; cleanup reported `kill EPERM`. Avi independently proved matching Chromium and WebKit can read a DOM outside this run. | `evidence/browser/report.json`, `debug/1/ledger.md`, Avi's independent runtime probe |

Matching Playwright browsers are now installed, but this managed run still cannot
create a context. The remaining resolution is to execute the unchanged suite
outside this sandbox. No static or DOM-only assertion is recorded as rendered verification.
Further post-commit secret, clean-checkout, live, cleanup, restart, and tag rows
will be appended only after observation.
