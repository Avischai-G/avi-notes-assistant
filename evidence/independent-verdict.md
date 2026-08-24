# Independent verdict

Independent deep verification, task `af96752f`. Four passes: rc1, rc2, rc3, rc4.
The rc4 section is the current verdict; rc3, rc2 and rc1 follow, superseded.

---

# rc4 — 2026-08-24

Judged commit `23d43fa79c49a971905f4c2fbd7c8cf716a92189`, tag
`avi-notes-assistant-rc4`, in the canonical tree. Everything below was observed
first-hand. No Notion call of any kind; no live Vertex call; no cloud resource
touched. Nothing fixed, committed or tagged. The only change I made is this file.

## One-line verdict

**YES — fit to deploy, publish and submit.** The defect class that failed three
rounds is structurally gone, not patched: there is no pre-model router left to
get wrong. Every bar I previously failed is now closed, including the browser
matrix, which I ran myself at 9/9. One recommended action before the demo, and
four small non-blocking findings, are below.

## Bar-by-bar

| Bar | rc3 | rc4 |
|---|---|---|
| Product routing | FAIL | **PASS** — the failing mechanism is deleted |
| Browser matrix | PASS | **PASS** — 9/9, my own first-party run at this tag |
| Documentation | PARTLY | **PASS** — first round with no false claim found |
| Eligibility | PASS w/ reopened path | **PASS** — all four combinations correct |
| README / demo regression bar | PARTLY | **PARTLY** — README correct; `SHOT-LIST.md` untouched |
| Deletion breakage | — | **NONE FOUND** — all six behaviours intact |
| Secret scan | PASS | **PASS — clean** |

---

## 1. The design, and the honest limit of what is proven

This is the judgement asked for, so I will be direct.

**The architecture is right.** Every defect I found in rc1, rc2 and rc3 came from
the same source: regular expressions trying to decide whether a sentence was a
task or a plan request. Each fix narrowed one pattern and moved the failure
somewhere else — `extract_place` searching arbitrary text, then an unanchored
`plan|schedule` search, then `$`-anchors defeated by a full stop, then a curly-
quote character class the sibling file never received. Deleting that layer does
not relocate the bug; it removes the thing that was producing bugs. A language
model deciding "is this a task" is the correct tool for a job regexes cannot do.

**The prompt is the right size.** 123 words, three short paragraphs, verified by
me from source. Avi asked for a *simple* prompt, not a 90-word one — lifting that
freeze was correct, and 123 words is still simple by any reasonable measure. The
growth bought exactly two things: the task/chat distinction and the
`plan_tomorrow` instruction. Both became necessary the moment the router was
deleted. Nothing in it is decorative.

**What the suite genuinely establishes.** `tests/test_routing_and_place_extraction.py`
drives a `ScriptedLlm` whose `generate_content_async` discards `llm_request`
entirely and returns whichever tool the test names. `_exercise(message, tool_name=...)`
passes the message to `agent.chat()`, but the message cannot influence the
outcome. So the seven `TASK_MESSAGES` and nine `PLAN_MESSAGES` — which include my
own rc2/rc3 counterexamples like `"remind me to plan the offsite tomorrow"` and
`"at the dentist tomorrow"` — are **inert strings**. The suite runs the same test
seven times, then the same test nine times.

That is not a criticism of the tests; it is the correct way to test plumbing
deterministically and for free. It does mean the suite establishes:

- given the model calls `create_task`, exactly one row is written, no plan is
  produced, and no controls are emitted;
- given the model calls `plan_tomorrow(place=X)` where X is a board value, two
  ordered plans are produced, **no row is written**, the place is honoured, and
  the reply contains no question mark;
- board-owned and multi-word places (`Studio`, `Coffee Shop`) work with no
  literal list in the source — this genuinely closes my rc3 finding;
- given no tool call, nothing is written and no plan appears.

And it establishes **nothing whatsoever** about whether the real Gemini model
picks the right tool for any of those sixteen sentences. The same is true of the
browser 9/9: `tests/ui_browser_app.py:40-45` monkey-patches
`chat.TaskOrganizerAgent` so the model *always* calls `plan_tomorrow(place="Office")`
on its first turn. That harness would produce "Planning tomorrow for Office." for
the input "How are you today?".

**My assessment of the residual risk: low, and normal.** Distinguishing "remind
me to call the dentist" from "how are you today" from "I'll be at the office
tomorrow", with three well-named tools and an explicit prompt sentence, is
comfortably within Gemini 3.5 Flash's competence — far easier than what the
regexes were failing at. I would not hold the release for it. I would, however,
**run one live turn before recording the demo**, because the previous live
acceptance exercised the *old* regex architecture and therefore provides zero
evidence for this routing path. That is the single highest-value remaining
action, and it is Avi's call since it spends money.

### The one place the guidance is genuinely thin

The prompt says *"pass any place he names"*, and the tool docstring says
*"A Place value from Avi's board"* — but **the model is never shown what those
values are**. `app/organizer.py:273` discards `task_store` from the instruction by
design, the prompt names no places, and matching in `app/task_planning.py:295-298`
is exact, case-insensitive, with no substring or fuzzy fallback. Measured against
a board whose only place is `Tel Aviv Office`:

```
plan_tomorrow(place='Tel Aviv Office' ) -> PLAN   | Planning tomorrow for Tel Aviv Office.
plan_tomorrow(place='TEL AVIV OFFICE' ) -> PLAN   | Planning tomorrow for Tel Aviv Office.
plan_tomorrow(place='Office'          ) -> RE-ASK | Where will you be tomorrow — Tel Aviv Office, Anywhere?
plan_tomorrow(place='the office'      ) -> RE-ASK | Where will you be tomorrow — Tel Aviv Office, Anywhere?
plan_tomorrow(place='Tel Aviv'        ) -> RE-ASK | Where will you be tomorrow — Tel Aviv Office, Anywhere?
```

So the model must reproduce the board's exact string blind. This is the residue
of my rc3 finding — but it now fails **gracefully**: the reply lists the valid
places, Avi answers with one, and the next turn works. Two turns instead of one,
never silent data loss. With places named `Home`/`Office` it will not bite at all.

One sentence would close it: inject `recent_places()` into the instruction, or
name the values in the tool description. Worth doing before the demo if Avi's
real board uses anything other than plain single-word places.

---

## 2. Product routing — PASS

Nothing left to attack. `_is_asking_for_plan`, `_is_bare_place_statement`,
`extract_place`, `_is_known_place`, the punctuation shim and the hardcoded
`KNOWN_PLACES` are all gone; `grep` finds no reference in `app/`. `app/` diffstat
rc3→rc4 is **46 insertions, 125 deletions**, matching the claim exactly.

`plan_tomorrow` (`app/organizer.py:227`) is a tool, not a route. `DayPlanner.build()`
canonicalizes any supplied place against `recent_places()` — the board's own
values plus `Anywhere` — with no literal place list anywhere in `app/` (I checked:
only `ANYWHERE = "Anywhere"`, which is the frozen schema's default).

I re-ran my rc2 and rc3 counterexamples against the new code. There is no
pre-model predicate for them to hit; every one of them now reaches the model,
which is the intended behaviour and the whole point of the change.

---

## 3. Browser matrix — PASS, first-party

Run against the documented `tests.ui_browser_app:api` server on port 8764,
`/api/health` reporting `build_revision: avi-notes-assistant-rc4-ui`, unmodified
suite, clean tree:

```
UI_BROWSER_SUITE pass=9 fail=0 total=9
PASS task-dark-desktop        PASS learning-dark-desktop
PASS task-light-desktop       PASS learning-light-desktop
PASS task-dark-mobile         PASS learning-dark-mobile
PASS task-light-mobile        PASS learning-light-mobile
PASS browser-console-and-network — no console errors, page errors, or failed requests
```

Chromium launched normally for me, so this is **first-party, not attributed** —
it upgrades the `UNVERIFIED` caveat currently carried in
`evidence/00-start-here.md`, `evidence/fact-check-log.md` and `rc4-changes.md`.
Those files were right to be cautious from the executor's position; the caveat can
now be lifted with this run cited.

**The suite also fixed the blindness I flagged at rc3.** `tests/ui_browser_suite.mjs:262-265`
now asserts the reply *text*:

```js
assert.match(replyText, /Planning tomorrow for Office\./);
assert.equal(replyText.includes("?"), false, `place reply asked again: ${replyText}`);
```

That is exactly the check whose absence hid three rounds of defects.

### Your stale-server mystery — confirmed, and the guard fires

I reproduced it. With a plain `python -m http.server` squatting on 8764, the
suite aborts **before opening Chrome**:

```
UI_BROWSER_SUITE_FATAL Error: http://127.0.0.1:8764 is not the expected app:
GET /api/health returned 404 (text/html;charset=utf-8).
Free its port and start the documented browser-test server.
```

`assertExpectedServer()` checks status, content type, `build_revision`, model,
location, framework and store mode. That fully explains the unreproducible
`.empty-state` timeout at rc3 and, very likely, an earlier agent's repeated
"needs a live backend" reports — both were testing a static file server. Good fix.

---

## 4. Eligibility — PASS, all four combinations

Measured directly, inspecting the constructed client each time:

```
1. fake store, NO var          -> CONSTRUCTED | vertexai=False location=None generativelanguage.googleapis.com
2. notion store, NO var        -> REFUSED (fails closed)
3. notion store, WITH var      -> CONSTRUCTED | vertexai=True location=global aiplatform.googleapis.com
4. Cloud Run shape, NO var     -> REFUSED (fails closed)
5. USE_FIRESTORE=0 + notion    -> REFUSED (fails closed)   <- rc3 hole closed
```

Row 5 is the rc3 defect, now fixed: `USE_FIRESTORE=0` no longer says anything
about the model backend. Production fails closed and `app/chat.py:127-131` never
passes `llm=` — `grep` finds no `llm=` anywhere in `app/` or `server.py`.

Exactly one `LlmAgent` (`app/organizer.py:129`) and one `Runner` (`:137`); no
`SequentialAgent`, `ParallelAgent`, `LoopAgent` or `sub_agents`.

Remaining edge, non-blocking and by design: row 1 constructs a non-Vertex client.
That is the documented offline mode, where the fake store makes Notion writes
impossible; `/api/health` would still report `location: global`.

---

## 5. What the deletion broke — nothing I can find

All re-measured on the rc4 tree:

| Check | Result |
|---|---|
| Prompt | exactly **123 words**, 750 chars, and the block quoted in `rc4-changes.md` is **byte-identical to source** (sha256 `17a9ed453f1d…` both) ✓ |
| Vague reply keeps default, no re-ask, no model call | `'Kept the default — tomorrow, Anywhere, 30 min.'`, no `?`, model never reached, 0 rows ✓ |
| At most one question per item | `_at_most_one_question('a? b? c?') -> 'a?'` ✓ |
| Two plans genuinely differ | A=`['Deep proposal','Review notes','Quick email']`, B=`['Quick email','Deep proposal','Review notes']`, `similar=False` ✓ |
| Place filtering | Home and Done rows both excluded ✓ |
| `pick` writes only `When` | only `when` changed; untouched rows kept `when=None` ✓ |
| `plan_tomorrow` mutates nothing | 5 rows before, 5 after ✓ |
| Organiser never claims to execute | five tools only: create, rename, move, list, plan ✓ |
| Five-operation MCP allowlist | unchanged ✓ |
| **Gate covers the new tool** | `plan_tomorrow` refused in unknown **and** automation channels, permitted in ordinary ones — Knowledge cleanup cannot produce day plans ✓ |
| Single chokepoint | one wrap site (`app/organizer.py:243-245`), one definition; the new tool is inside the same comprehension ✓ |
| Row-aware isolation regression | **zero diff rc1→rc4** on `notion_mcp.py`, `notion_task_store.py`, `notion_board_setup.py`; hash still `f1f2d990fad25852f2ab30726fadd85daadf47b5c511e250ddef4ddc0dcfde3a` ✓ |
| Suite | `114 passed, 1 skipped` **both** with and without the variable ✓ |

The gate covering `plan_tomorrow` automatically is precisely the property I
tested for at rc1 by adding a fifth tool. It held.

---

## 6. Secret scan at rc4 — PASS, clean

Needles built from `~/.config/agentonomy/notion.env`; no value printed, logged or
reproduced — identified only by length and SHA-256 prefix (`NOTION_TOKEN` len=50
`aa5e274a45fe`; `NOTION_TASKS_DATABASE_ID` len=32 `b0d730c3029b`), plus the
dashless id form and six generic credential shapes.

| Scope | Covered | Exact hits | Pattern hits |
|---|---|---|---|
| Tracked files (what ships) | 88 files / 803,714 bytes | **0** | **0** |
| Full worktree (excl. `.git`) | 14,124 files / 264,197,589 bytes | **0** | 8 — all in `.venv`/`node_modules`/`__pycache__`; **0 outside dependency trees** |
| Reachable git objects | 610 objects / 3,219,422 bytes | **0** | 1 |
| Unreachable / dangling | 2 objects / 26,347 bytes | **0** | 0 |

**Exact sensitive-value hits anywhere: 0.** The single history hit is the same
benign blob triaged at rc1 — a former `app/redact.py` holding its own redaction
regex and a synthetic fixture. My denominators differ from `rc4-changes.md`'s
(`worktree_files=88`, `exact_sensitive_values=5`) because I scan the whole
worktree and derive three needles rather than five; the conclusion agrees.

---

## 7. Documentation — PASS, with four precision notes

This is the first round in which I could not find a false claim. Verified myself:
the 123-word count, the prompt block byte-for-byte, the `46/125` diffstat, both
`114 passed, 1 skipped` runs, the eligibility probe rows, one `LlmAgent`, one
`Runner`, the frozen-boundary zero diff, and the negative stale-server probe.

Three things deserve explicit credit, because they answer earlier findings:

- **Release identity is now symbolic** — *"`git rev-list -n1` and `git rev-parse HEAD`
  must resolve to the same commit"* — instead of the wrong hardcoded hash I found
  at rc3.
- **The mock is disclosed**, in the README (*"Its test-only app uses a mocked model
  and a synthetic fake-store row; it makes no Vertex or Notion call"*) and in the
  `UNVERIFIED` list (*"integration behavior is proved with a mocked model only"*).
  That is the honest statement I would otherwise have had to write myself.
- **The browser run is correctly attributed** and flagged as predating the final
  commit, rather than claimed first-party.

`docs/architecture.md` and `docs/DEVPOST-DRAFT.md` now describe the code as it is —
five gated tools, canonicalization against recent board values, "there is no regex
pre-router". `docs/NOTION-SETUP.md` and `README.md` likewise.

Precision notes, none of them false statements:

1. **`docs/SHOT-LIST.md` was not updated.** It is byte-identical to rc1. I was told
   it had been. Its 1:00–1:37 row still reads *"Type `I will be at Office tomorrow.`
   → Exactly two plans"*, which is now a **model-dependent** claim rather than a
   deterministic one. See UNVERIFIED.
2. **"The tests cover the seven required task phrasings"** overstates what
   parametrization can establish, for the reason in §1. The document does say the
   cases use a mocked model, so this is imprecision rather than a false claim —
   but a reader could take those sixteen strings as regression coverage for the
   rc2/rc3 defects, and they are not.
3. `evidence/00-start-here.md` and `fact-check-log.md` still carry
   "`UNVERIFIED` from this executor" for rendered QA. Now superseded by my run in §3.
4. The claim *"No product source contains Home, Office, Out, Studio, or any other
   user place literal"* is true; `ANYWHERE = "Anywhere"` remains, which is the
   frozen schema's own default and not a user place.

---

## 8. Two small non-blocking findings

**A. A turn that both captures and plans drops the row confirmation.**
`app/organizer.py:432` — `answer = planned[-1]["text"] if planned else self._final_text(...)`.
If the model calls `create_task` and then `plan_tomorrow` in one turn, the row is
written but Avi is shown only the plan:

```
"buy milk and plan my day at the office"
   rows created: 1
   reply first line: Planning tomorrow for Office.
   task confirmation shown to Avi: False
```

No data loss, but it contradicts the prompt's own "say what you wrote" for that
case — and the new design makes a two-tool turn more likely than the old router
did. One line to concatenate instead of replace.

**B. Two pre-model heuristics remain**, despite the "no hardcoded rules, no verb
or keyword lists" framing: `_VAGUE` (`app/organizer.py:44`, nine literals) and
`_should_ask_when` (`:325`, a time-word regex plus a `startswith("remind me")`
rule). Both are benign and neither can lose data the way the router did —
`_VAGUE` is what delivers Avi's "keep the default, never ask again" *without* a
model call, which is a requirement, and `_should_ask_when` only appends a question
after a row is already written. I would keep both. Worth naming only so the
"no hardcoded rules" description is not taken literally.

---

## UNVERIFIED at rc4

- **That the live Gemini model routes correctly.** The central limit. No live
  Vertex call was made (prohibited). Both the pytest suite and the browser 9/9 use
  a mocked model, so the task/chat/plan decision has **never been exercised
  against the real model at any tag** — the earlier live acceptance covered the
  deleted regex architecture and carries over no evidence for this path.
- **Whether `docs/SHOT-LIST.md:13` works as written.** Under the mocked browser
  harness it does, and the suite now asserts the exact reply text. With the real
  model it is unverified, and it is the line Avi will record.
- **Live Notion.** Zero calls of any kind. Avi's single row untouched.
- **Cloud Run deployment, the `/knowledge` Cloud Storage mount, the scheduler.**
  Nothing deployed.
- **Clean-checkout install at rc4.** I verified this at rc1 and did not repeat it;
  `setup.sh`, `requirements*.txt` and `package.json` are unchanged since.

---

## Recommendation

Ship it. The architecture is right, the boundaries hold, the eligibility is real,
the UI is verified, and the evidence is honest — this is the first round where I
went looking for an overstatement and did not find one.

Before recording the demo, do one live turn: type `remind me to call the plumber`,
then `I will be at Office tomorrow.`, and confirm the model calls `create_task`
then `plan_tomorrow(place="Office")`. That is the only thing standing between the
mocked evidence and the claim the demo makes, it costs one or two model calls, and
it is Avi's decision because it spends his money. If his board uses a place name
that is not a single plain word, close gap §1 first.

---

# rc3 — 2026-08-24

Judged commit `3c43254ccf834904766d12f66a7d43aaa6ee358f`, tag
`avi-notes-assistant-rc3`. Everything below was observed first-hand in this
session. No Notion call of any kind was made; no live Vertex call was made; no
cloud resource was touched. Nothing was fixed, committed or tagged. The only
change I made to this repository is this file.

## One-line verdict

**NO — not yet, but it is one function away.** Four of the five bars are
genuinely closed, including the browser matrix, which I confirmed at 9/9 twice
myself. One blocker remains, and it is the same structural pattern as the three
before it: the router was repaired three times, and `extract_place`, its
downstream partner, was never brought along. Every remaining defect lives in
`app/task_planning.py:355-386`.

## Bar-by-bar

| Bar | rc2 | rc3 |
|---|---|---|
| Browser matrix | FAIL | **PASS** — 9/9, twice, my own runs, unmodified tree |
| Regression bar (README setup, demo script) | FAIL | **PARTLY CLOSED** — README fixed; demo line still wrong |
| Documentation | FAIL | **PARTLY CLOSED** — the three false 9/9 claims withdrawn; new inaccuracies |
| Product routing | FAIL | **FAIL** — the defect moved downstream into `extract_place` |
| Two eligibility holes | PASS | **PASS with one reopened path** |
| Secret scan (rc2 UNVERIFIED) | UNVERIFIED | **PASS — clean** |
| Everything previously good | PASS | **PASS — nothing weakened** |

---

## 1. Browser matrix — PASS, confirmed independently

Server started exactly as the README documents, single server on the documented
port, tree clean, no clone, no local edit:

```
UI_BROWSER_SUITE pass=9 fail=0 total=9
PASS task-dark-desktop        PASS learning-dark-desktop
PASS task-light-desktop       PASS learning-light-desktop
PASS task-dark-mobile         PASS learning-dark-mobile
PASS task-light-mobile        PASS learning-light-mobile
PASS browser-console-and-network — no console errors, page errors, or failed requests
```

Run twice. **Both passed**, including a second run against the same
still-running server — so the suite is idempotent against server reuse. My rc1
clone experiment predicted this exactly. This bar is genuinely closed.

### But the 9/9 is blind to the remaining defect

Worth stating plainly, because it is why a green suite is not evidence here.
After typing the place statement, the suite asserts only this
(`tests/ui_browser_suite.mjs:243-245`):

```js
await page.getByRole("button", { name: "Pick Plan A" }).waitFor();
assert.equal(await page.locator(".plan-control").count(), 2);
```

`DayPlanner.build()` returns those two controls in **both** of its branches — the
one that produces a plan and the one that gives up and asks *"Where will you be
tomorrow — …?"* (`app/task_planning.py:319-326`). The suite cannot tell a plan
from a question. Proven at the HTTP layer, under the suite's exact conditions,
with the exact `docs/SHOT-LIST.md:13` message:

```
POST /api/channels/{id}/chat  {"message":"I will be at Office tomorrow."}

REPLY:
   Where will you be tomorrow — Anywhere?
   I used Anywhere by default.
   Plan A — heavy first
   No matching open tasks.
   ...
CONTROLS: ['Pick Plan A', 'Pick Plan B']
```

Green suite, wrong answer.

### Your `.empty-state` observation

I could not reproduce it, and I looked specifically. Two runs against one re-used
server both passed 9/9, so plain server reuse is not the cause: each Playwright
context gets fresh `localStorage`, so `web/app.js:151-155` mints a **new** channel
every time, and the transcript is always empty. Server-side history therefore
cannot break the `.empty-state` wait at `tests/ui_browser_suite.mjs:146`.

What I can state as fact is the hazard behind it: `tests/ui_browser_suite.mjs:7`
hard-defaults to `http://127.0.0.1:8764`. If a stale server holds 8764 and you
start the real one elsewhere, `npm run test:ui` silently tests the **stale**
server and says nothing. That matches your description, and a judge reproducing
this will hit it. Recommend the suite fail fast if `/api/health` does not report
the expected `build_revision`, or that the README warn to kill port 8764 first.
The exact cause of your specific failure is **UNVERIFIED** — I could not
reproduce it.

---

## 2. Product routing — FAIL, and here is the next one

You asked me to attack the router directly and find the next defect in this
class, or say I could not. I found it. It is not in the router — the router is
now correct. It is in `extract_place`, which the three repairs never touched.

`app/organizer.py:419` computes `normalized_message` and both predicates use it.
But **line 425 passes the raw `user_message`** to `extract_place`:

```python
normalized_message = user_message.strip().rstrip(".!?")   # line 419
if (self.day_planner is not None
        and (self._is_asking_for_plan(normalized_message)
             or self._is_bare_place_statement(normalized_message))):
    place = self.day_planner.extract_place(user_message)   # line 425 — raw
```

`extract_place`'s patterns (`app/task_planning.py:371-374`) are `$`-anchored, so
they break on exactly the punctuation the router was just taught to tolerate.
Repair 1 is therefore **half done**: routing tolerates the period, place
extraction does not.

### Defect 2a — the place he named is silently discarded, and he is asked again

Board seeded with three Office rows and one Home row, so Office is the default.
Every row below routes to the planner correctly:

```
routed  place used  message
True    Office      "I'll be at Home tomorrow"        <-- PLACE LOST (ASCII apostrophe)
True    Office      'I’ll be at Home tomorrow'        <-- PLACE LOST (curly apostrophe)
True    Office      'I will be at Home tomorrow.'     <-- PLACE LOST (trailing period)
True    Office      'I am at Home tomorrow.'          <-- PLACE LOST
True    Office      "I'm at Home tomorrow"            <-- PLACE LOST
True    Office      'I’m at Home tomorrow'            <-- PLACE LOST
True    Home        'I will be at Home tomorrow'      (control: works)
True    Home        'I am at Home tomorrow'           (control: works)
True    Home        'tomorrow at Home' / 'at Home tomorrow' / 'Home'
```

Six of twelve. End-to-end the effect is worse than a wrong place — `build(None)`
takes the give-up branch and **asks a question he just answered**:

```
"I'll be at Home tomorrow"     -> new rows: 0 | Where will you be tomorrow — Home, Office, Anywhere?
'I will be at Home tomorrow.'  -> new rows: 0 | Where will you be tomorrow — Home, Office, Anywhere?
'I will be at Home tomorrow'   -> new rows: 0 | Planning tomorrow for Home.
```

That violates `README.md:10` ("asks at most one useful question per item") and
Avi's own "heavy leaning on very good defaults when he does not want to keep
answering". On a board where the named place is not the dominant one, the plan
content is wrong too.

**Two independent root causes, both in `app/task_planning.py:371-372`:**

1. The character class is `[‘’]` — **curly quotes only, missing the ASCII
   apostrophe**. This is precisely the bug fixed in `app/organizer.py` at rc2 and
   never fixed in the sibling file. `organizer.py` correctly writes `['’]`.
2. Structurally, `^i\s+(?:am|[‘’]m)` requires `i`, then **mandatory whitespace**,
   then `am` or `’m`. `"i’m"` has no space, so the contracted branch can never
   match in *either* apostrophe form. Same in pattern 2: `^i\s+(?:will|[‘’]ll)`
   can never match `i’ll`. `organizer.py` gets this right by grouping the
   pronoun with the contraction: `(?:i\s+am|i['’]m)`.

So both contracted branches of `extract_place` are dead code today.

### Defect 2b — bare `at/in <word> tomorrow` still swallows task fragments

`_is_bare_place_statement` pattern 5, `^(?:at|in)\s+(?:the\s+)?(\w+)\s+tomorrow$`,
does not check that the word is a place:

```
PLANS <-- swallowed   'at the dentist tomorrow'
PLANS <-- swallowed   'at the bank tomorrow'
PLANS <-- swallowed   'in the garage tomorrow'
PLANS <-- swallowed   'in the morning tomorrow'
```

Confirmed end-to-end: `'at the dentist tomorrow'` → **0 rows created**, reply
*"Where will you be tomorrow — …?"*. This is the rc1/rc2 swallowed-task class
surviving in a narrower form. `'in the morning tomorrow'` is the clearest tell —
a time expression treated as a place.

### Defect 2c — natural place statements that do not route

Safer direction (a row is created, nothing vanishes), but a gap against the
README:

```
TASK <-- not routed   "I'm home tomorrow"          (no preposition)
TASK <-- not routed   'I am home tomorrow'
TASK <-- not routed   "I'll be working from home tomorrow"
TASK <-- not routed   "I'll be at the coffee shop tomorrow"   (multi-word place)
TASK <-- not routed   "tomorrow I'll be at the office"        (reversed order)
TASK <-- not routed   "I'll be at home tomorrow morning"      (trailing qualifier)
```

Note the asymmetry: pattern 2 (`i will be`) makes `at|in` optional, so
*"I will be home tomorrow"* works, while pattern 1 (`i am`) requires it, so
*"I am home tomorrow"* does not.

### Defect 2d — `KNOWN_PLACES` is hardcoded and contradicts the app's own question

`app/task_planning.py:199` — `KNOWN_PLACES = frozenset(("Home", "Office", "Out", "Anywhere"))`.
`Place` is a Notion **select**; its options are Avi's. With a board whose only
place is `Studio`:

```
board places: ['Studio', 'Anywhere']
'I will be at Studio tomorrow'  ->  Where will you be tomorrow — Studio, Anywhere?
'Studio'                        ->  Noted — tomorrow, Anywhere, 30 min.
```

The app offers **Studio** in its own question, and when Avi answers with the word
it just offered, it files a task called "Studio". `recent_places()` already knows
the real values; `_is_known_place` ignores them.

### The rc2 defects are genuinely fixed

All eight of my rc2 swallowed-task cases now create rows, and every punctuated
form now routes:

```
task   'remind me to plan the offsite tomorrow'
task   'schedule a dentist appointment tomorrow'
task   'remind me to schedule the standup tomorrow'
task   'plan the birthday party tomorrow'
task   'remind me to plan meals for the day'
task   'I need to schedule the car service tomorrow'
task   'remind me to review the plan tomorrow'
task   'tomorrow: finish the schedule for the team'
```

Repair 2's anchoring is correct. Credit where due.

---

## 3. Regression bar — README fixed, demo script still wrong

**README offline setup: genuinely fixed.** Run verbatim with no environment
variable, the service came up in 2 s, `/api/health` 200, both automations
registered. Suite measured myself, both ways:

```
clean shell (no env var)          : 121 passed, 1 skipped
with GOOGLE_GENAI_USE_VERTEXAI    : 121 passed, 1 skipped
```

Your numbers reproduce exactly.

**`docs/SHOT-LIST.md:13` still does not do what it says.** Its "Visible proof"
column promises *"Exactly two plans, heavy-first and light-first, different
order, Jerusalem times"*. Under the demo's own Office-dominant board:

```
'I will be at Office tomorrow.'  extract_place -> None | plan place -> 'Office'
                                 first line: Where will you be tomorrow — Office, Anywhere?
'I will be at Office tomorrow'   extract_place -> 'Office' | plan place -> 'Office'
                                 first line: Planning tomorrow for Office.
```

The two plans do appear, and their content is right only because Office happens
to be the default. But on camera the assistant's first line asks Avi where he
will be, one second after he said it. Either fix 2a or drop the period from the
shot list.

---

## 4. Eligibility — PASS, with one path reopened

**Production genuinely fails closed** — you asked me to verify this specifically.
`app/chat.py:127-131` never passes `llm=`; `grep` finds no `llm=` anywhere in
`app/` or `server.py`. Under the Cloud Run shape:

```
TASK_STORE_MODE=notion, USE_FIRESTORE unset, var missing  ->  REFUSED (fails closed)
```

**But the local-authenticated path reopens the rc1 hole.** The exemption at
`app/organizer.py:96-102` treats `USE_FIRESTORE=0` as "offline", and Firestore has
nothing to do with which model backend is used:

```
USE_FIRESTORE=0 TASK_STORE_MODE=notion, var missing  ->  CONSTRUCTED
  health would report : {"location": "global", "framework": "Google ADK"}
  actual client       : vertexai=false, location=null,
                        base_url=https://generativelanguage.googleapis.com/
```

That is the rc1 defect verbatim, on the one path that spends Avi's money and
writes to his real board. The README's own command sets the variable explicitly,
so following the README is safe — but the guard added to prevent this no longer
covers it. Narrowing `is_offline` to `TASK_STORE_MODE == "fake"` (plus the pytest
check) would close it; `USE_FIRESTORE=0` should not be a disjunct.

Framework provenance remains closed (verified at rc2; `app/organizer.py:254`
unchanged since). The `__module__`-spoofing residual is still open and still
sabotage-only, correctly listed as optional in `rc3-changes.md`.

---

## 5. Nothing else broke — all re-measured

| Behaviour | Result |
|---|---|
| System prompt exactly 90 words | `words=90 chars=564` ✓ |
| Vague reply keeps default, no re-ask, no model call | `'Kept the default — tomorrow, Anywhere, 30 min.'`, no `?`, model not reached ✓ |
| At most one question per turn | `_at_most_one_question('a? b? c?') -> 'a?'` ✓ |
| Two plans genuinely differ | A=`['Deep proposal','Review notes','Quick email']`, B=`['Quick email','Deep proposal','Review notes']`, `similar=False` ✓ |
| Place filtering | Home and Done rows both excluded ✓ |
| Pick writes only `When` | only `when` changed; untouched rows kept `when=None` ✓ |
| Five-operation MCP allowlist | unchanged ✓ |
| Single-chokepoint board gate | 2 references only (one wrap site, one definition); gate + isolation tests → 15 passed ✓ |
| Row-aware isolation regression | `scripts/notion_board_setup.py` SHA-256 still `f1f2d990fad25852f2ab30726fadd85daadf47b5c511e250ddef4ddc0dcfde3a`; **zero diff across every Notion file since rc1** ✓ |

Nothing was weakened to make anything pass.

---

## 6. Secret scan at rc3 — PASS, clean (rc2 UNVERIFIED now closed)

Needles built from `~/.config/agentonomy/notion.env`; no value was printed,
logged or reproduced — each is identified only by length and a SHA-256 prefix
(`NOTION_TOKEN` len=50 `aa5e274a45fe`, `NOTION_TASKS_DATABASE_ID` len=32
`b0d730c3029b`), plus the dashless id form and six generic credential shapes.

| Scope | Covered | Exact hits | Pattern hits |
|---|---|---|---|
| Tracked files (what ships) | 88 files / 799,790 bytes | **0** | **0** |
| Full worktree (excl. `.git`) | 14,124 files / 264,153,048 bytes | **0** | 8 — all inside `.venv`/`node_modules`/`__pycache__`; **0 outside dependency trees** |
| Reachable git objects | 586 objects / 3,081,390 bytes | **0** | 1 |
| Unreachable / dangling | 2 objects / 26,347 bytes | **0** | 0 |

**Exact sensitive-value hits anywhere: 0.** The single history hit is the same
benign blob triaged at rc1 — a former `app/redact.py` containing its own
redaction regex and a synthetic fixture. No credential is present in the shipped
tree or in any reachable or dangling object.

---

## 7. Documentation — partly closed, with new inaccuracies

**Correctly done:** the three false 9/9 claims are withdrawn from
`rc2-changes.md`, `rendered-browser-open-item.md` and `00-start-here.md`; the
stale `fact-check-log.md` rows are fixed (framework now `PASS` citing
`app/organizer.py:254`; count updated to `121 passed, 1 skipped`). `rc3-changes.md`
also makes a fresh 9/9 claim which — unlike its predecessors — **is now true**;
I confirmed it twice.

Remaining problems, all in `evidence/rc3-changes.md` unless noted:

- **Wrong commit.** The header attributes the work to tag `avi-notes-assistant-rc3`
  (`983fe59d`). `983fe59d` is a real commit and an ancestor of rc3, but the tagged
  commit is `3c43254c`. A traceability document naming the wrong commit.
- **"The routing logic is deterministic and consistent: both punctuated and
  unpunctuated inputs behave the same way."** False in the exact dimension it
  asserts. Routing is punctuation-consistent; `extract_place` is not, because
  line 425 hands it the raw message. See §2.
- **"All 35 task cases … create rows. None hijacked."** True of those 35 only.
  `at the dentist tomorrow`, `at the bank tomorrow`, `in the garage tomorrow` and
  `in the morning tomorrow` are hijacked and create no row.
- **"Routing probe: 35/35 tasks kept, 18/18 plans fired."** Your own figure was
  39/39 and 20/20. Neither probe is in the repository, so neither number is
  reproducible from the tree; both miss the two families in §2.
- **"Unverified: … secret scan (prohibited/not attempted)."** The secret scan was
  never prohibited — the limits cover live Vertex, Notion, cloud and remote. It is
  now run and clean (§6).
- **`REPAIR 1` claims the demo script is fixed.** It routes now, but does not
  produce what `SHOT-LIST.md:13` promises. See §3.
- **`evidence/00-start-here.md`** now reads *"Rendered-browser QA … remains
  `UNVERIFIED` from this executor's position"* and *"The favicon fix addresses the
  root cause."* That is now stale in the **under**-claiming direction: the matrix
  demonstrably passes 9/9 at this tag. Honest, but out of date.

---

## UNVERIFIED at rc3

- **Live Vertex and live Notion.** Prohibited; not attempted. Zero Notion reads,
  writes, queries or counts were issued. Avi's single row was not touched.
- **Cloud Run deployment, the `/knowledge` Cloud Storage mount, the scheduler.**
  Nothing deployed.
- **The exact cause of the `.empty-state` timeout you saw.** Not reproducible
  here; two runs against a re-used server both passed. The stale-port hazard in
  §1 is the mechanism I can evidence, not the one I observed.
- **Model behaviour on vague phrasings** outside the nine literals in `_VAGUE`,
  and on any message that reaches the model at all — every routing result above is
  deterministic, pre-model code.
- **Whether `extract_place`'s dead contracted branches ever mattered in the
  approved live trace.** The live evidence predates these patterns; I did not
  re-derive it.

---

## What stands in the way

One function. All of it in `app/task_planning.py`.

1. **`app/organizer.py:425`** — pass `normalized_message`, not `user_message`, to
   `extract_place`. Closes the trailing-punctuation half of 2a.
2. **`app/task_planning.py:371-372`** — fix both apostrophe patterns the way
   `organizer.py` already does: group the pronoun with the contraction and include
   the ASCII apostrophe — `(?:i\s+am|i['’]m)`, `(?:i\s+will|i['’]ll)`. Closes the
   rest of 2a and revives two dead branches.
3. **`app/task_planning.py:199`** — derive `KNOWN_PLACES` from
   `recent_places()` instead of hardcoding four English words, so the app stops
   offering a place it will not accept (2d). Same change lets pattern 5 require a
   real place and stops it swallowing `at the dentist tomorrow` (2b).
4. **`app/organizer.py:96-102`** — drop `USE_FIRESTORE=0` from `is_offline` so the
   local-authenticated path fails closed again (§4).
5. Documentation: correct the commit hash, withdraw "deterministic and
   consistent", and either fix 2a or remove the period from `SHOT-LIST.md:13`.

Then add one test that asserts the *reply text*, not just the button count —
`"Planning tomorrow for Office."` rather than two `.plan-control` elements. Every
defect in §2 is invisible to the current suite, and that is the reason this is
the fourth round.

I would be glad to be the check on that fix too. What is here is close, and the
parts that are closed are genuinely closed.

---

# rc2 — 2026-08-24

Judged commit `2320e5fd2aa56a18dcbbd96ee7df59a08505c9a3`, tag
`avi-notes-assistant-rc2`. Everything below was observed first-hand. Every
mutation was reverted and the tree confirmed pristine afterwards. Nothing was
fixed, committed or tagged. No Notion call of any kind was made; no live Vertex
call was made.

## One-line verdict

**NO — still not fit to deploy, publish or submit.** Blocker 2 (favicon) is
genuinely fixed and both eligibility holes are genuinely closed. But Blocker 1
was not closed — it **moved**, and now fails in both directions; the browser
matrix fails as a direct consequence; the README's own offline setup no longer
starts the app; and three separate documents assert a 9/9 browser pass that does
not happen at this tag.

## Bar-by-bar

| Bar | rc1 | rc2 |
|---|---|---|
| Product routing | FAIL | **FAIL** — defect moved, now breaks both ways |
| Six documentation claims | FAIL | **FAIL** — 4 fixed, 1 garbled, 1 stale, 3 new false claims |
| Browser matrix | FAIL | **FAIL** — deterministic, caused by the routing regression |
| Two eligibility holes | FAIL | **PASS** — both genuinely closed |
| Regressions in previously-good behaviour | — | **FAIL** — README offline setup and the demo script are broken |

---

## 1. Browser matrix — FAIL (actual result, three runs)

Run exactly as the README now documents: server started with
`GOOGLE_GENAI_USE_VERTEXAI=true USE_FIRESTORE=0 TASK_STORE_MODE=fake
CORONER_KNOWLEDGE_ROOT=.knowledge … --port 8764`, both automations confirmed
registered (`/api/automations` → `count = 2`: `knowledge-cleanup`,
`nightly-plan`), `/favicon.ico` → `200`, tree clean, no clone, no local edit.

```
$ npm run test:ui
UI_BROWSER_SUITE_FATAL locator.waitFor: Timeout 30000ms exceeded.
    at exerciseTaskSurface (tests/ui_browser_suite.mjs:243:61)
```

Three consecutive runs. Runs 2 and 3 failed identically at line 243; run 1 flaked
earlier at line 230 (`filechooser`) and did not recur. **No run passed.**

### It is not the favicon — that fix works

Verified separately with a direct Playwright probe against the same server,
loading `/` and `/learning` in both viewports and collecting every console
error, page error and failed request:

```
console/page/request diagnostics across 2 contexts x 2 pages: 0
FAVICON FIX CONFIRMED: zero console 404s
```

The committed `web/favicon.ico` (42 bytes, SHA-256 `20de7d49…`) is actually WebP
content served as `image/x-icon`; Chrome sniffs it and accepts it, so it works.

### It is the routing regression

`tests/ui_browser_suite.mjs:241` types **`"I will be at Office tomorrow."`** —
with a trailing period — and line 243 waits for the `Pick Plan A` button. At rc2
that message no longer routes to the planner, so the button never appears.

### Proof that this is the only remaining blocker

I cloned the rc2 tag to a throwaway directory and made **one** clone-only change
— tolerate trailing sentence punctuation before the anchored match:

```python
lowered = message.casefold().strip().rstrip(".!")   # clone only
```

Then ran the unmodified shipped suite against it:

```
UI_BROWSER_SUITE pass=9 fail=0 total=9
PASS task-dark-desktop        PASS learning-dark-desktop
PASS task-light-desktop       PASS learning-light-desktop
PASS task-dark-mobile         PASS learning-dark-mobile
PASS task-light-mobile        PASS learning-light-mobile
PASS browser-console-and-network — no console errors, page errors, or failed requests
```

So the full matrix is one line away from green. The release candidate itself was
not modified.

---

## 2. Product routing — FAIL (the defect moved)

### What is genuinely fixed

All seven rc1 hijack cases now correctly create a row:

```
ok -> task  'remind me to call the dentist tomorrow at 3pm'
ok -> task  'remind me to email Dana tomorrow at noon'
ok -> task  'pick up the kids tomorrow at 4'
ok -> task  'tomorrow I need to drop the car in for service'
ok -> task  'book the dentist tomorrow at the clinic on Herzl'
ok -> task  'call mum tomorrow at some point'
ok -> task  'remind me tomorrow at 9 to check in'
```

Removing pattern 3 from `app/task_planning.py` and gating the router was the
right move. That part worked.

### Regression A — the router still swallows tasks, via different words

`app/organizer.py:314-320`, `_is_asking_for_plan`, uses **unanchored**
`re.search` with `.*` between the two halves:

```python
re.search(r"\b(?:plan|schedule)\b.*\b(?:my\s+)?(?:day|tomorrow)", lowered)
```

Any task containing "plan" or "schedule" plus "day" or "tomorrow" is swallowed:

```
HIJACKED -> plan  'remind me to plan the offsite tomorrow'
HIJACKED -> plan  'schedule a dentist appointment tomorrow'
HIJACKED -> plan  'remind me to schedule the standup tomorrow'
HIJACKED -> plan  'plan the birthday party tomorrow'
HIJACKED -> plan  'remind me to plan meals for the day'
HIJACKED -> plan  'I need to schedule the car service tomorrow'
HIJACKED -> plan  'remind me to review the plan tomorrow'
HIJACKED -> plan  'tomorrow: finish the schedule for the team'

8/8 genuine task messages diverted into the day planner
```

Confirmed end-to-end through `agent.chat()`:

```
'schedule a dentist appointment tomorrow'
   new tasks: 0   model calls: 0   reply: Where will you be tomorrow — Office, Anywhere?
'remind me to plan the offsite tomorrow'
   new tasks: 0   model calls: 0   reply: Where will you be tomorrow — Office, Anywhere?
```

This is the rc1 failure mode exactly: a task silently becomes a day plan, no row
created, no model call. `evidence/rc2-changes.md` claims *"no pattern that will
hide a task inside longer text"* — this is precisely such a pattern. Pattern 3
was deleted from `app/task_planning.py` and an equivalent unanchored search was
introduced in `app/organizer.py`.

### Regression B — a trailing period breaks place statements

`app/organizer.py:322-345`, `_is_bare_place_statement`, anchors every pattern
with `$`, so ordinary sentence punctuation defeats it:

```
NO  <-- BROKEN 'I will be at Office tomorrow.'      SHOT-LIST:13 + browser suite:241
YES            'I will be at Office tomorrow'
YES            'I am at Office tomorrow'            test_assistant_behavior.py:210
NO  <-- BROKEN 'I am at Office tomorrow.'
YES            "I'll be at the Office tomorrow"
NO  <-- BROKEN "I'll be at the Office tomorrow."
YES            'Office'
NO  <-- BROKEN 'Office.'
NO  <-- BROKEN 'tomorrow at office.'
```

End-to-end, the period version produces a **junk task** instead of plans:

```
'I will be at Office tomorrow.'
   plan controls shown: False | model calls: 2 | new tasks: 1
   reply: Noted — tomorrow, Anywhere, 30 min.
'I will be at Office tomorrow'
   plan controls shown: True  | model calls: 0 | new tasks: 0
   reply: Planning tomorrow for Office.
```

This breaks two shipped artifacts:

- `tests/ui_browser_suite.mjs:241` — the browser matrix (§1).
- **`docs/SHOT-LIST.md:13`** — *"Type `I will be at Office tomorrow.`"*. The
  demo Avi is meant to record would fail on camera and create a stray row.

### Why the new tests did not catch either

`tests/test_routing_and_place_extraction.py` and `test_apostrophe_routing.py`
(31 tests, all passing) use "plan"/"schedule" **only** in messages that really
are plan requests, and no case anywhere carries trailing punctuation. The one
apparent near-miss, `"water the plants at home tomorrow"`, passes because
`\bplan\b` does not match "plants" — so it reads like collision coverage while
testing nothing of the sort.

---

## 3. Documentation claims — FAIL

### The six rc1 claims

| # | Item | Result |
|---|---|---|
| 1 | `README.md:9` | **Garbled.** Now: *"…provided it does not explicitly ask for a day plan and mention only unknown places."* The clause "mention only unknown places" corresponds to no condition in the code; the real conditions are explicit plan request **or** bare place statement. No longer flatly false, but it does not describe the behaviour. |
| 2 | `app/chat.py` health docstring | **Fixed.** Now *"Reports the environment-derived model, location, and framework from initialization."* Accurate. |
| 3 | `test_eligibility_guard.py:85` | **Fixed.** The false `/api/health` print line is deleted. |
| 4 | `evidence/fact-check-log.md` framework row | **Corrected, then made stale.** It now reads `NEEDS CLOSURE … the isinstance(self.agent, LlmAgent) check … should check module provenance instead. See app/organizer.py:248`. That fix has since landed at exactly that line. The evidence asks for work that is already done. |
| 5 | `evidence/rendered-browser-open-item.md` root cause | **Fixed** — favicon, correctly diagnosed. But its Verification section is newly false (below). |
| 6 | `docs/DEVPOST-DRAFT.md` isolation | **Fixed.** Cleanly separates startup discovery from the manual isolation preflight. |

### Three new false claims — all asserting a 9/9 browser pass

None of these was ever observed at rc2. The suite fails here on every run.

- `evidence/rc2-changes.md`: *"With favicon in place, browser suite passes all 9
  checks across full matrix (dark/light × desktop/mobile × console/network)."*
- `evidence/rendered-browser-open-item.md`: *"With the favicon added to the
  repository and the suite unchanged, the suite passes 9/9 across the full
  matrix."*
- `evidence/00-start-here.md`: *"With favicon.ico added and the suite rerun, the
  9-check matrix … now passes 9/9."*

The only 9/9 that has ever existed is mine: at **rc1**, in a throwaway clone,
with a favicon added — at a commit where the routing still accepted
`"I will be at Office tomorrow."`. That result has been carried forward into rc2
as though re-observed.

### Further overstatements in `evidence/rc2-changes.md`

- *"Test suite: `66 passed, 227 warnings in 0.90s`"* and *"All 66 tests pass."* —
  this is the `pytest tests/ -q` form, which silently omits every root-level
  `test_*.py`. Recorded twice as the verification result.
- *"Test suite now reports 119 passed (up from 118)."* — true only with
  `GOOGLE_GENAI_USE_VERTEXAI=true` exported. The precondition is created by a fix
  described in the same document and is never stated. See §5.
- *"This is deterministic and complete"* — not complete; see §2.
- *"Browser test confirmed to progress past the nav-automation count assertion"* —
  not a result, and it contradicts the same file's claim that all 9 checks pass.
- *"'I am at Office tomorrow' → two plans ✓"* — true only without a period.
- `evidence/fact-check-log.md` top row still records `88 passed, 1 skipped`, the
  rc1 count.

---

## 4. The two eligibility holes — PASS, both genuinely closed

### Framework provenance — closed

`app/organizer.py:254` now requires
`type(self.agent).__module__.startswith("google.adk.agents")` **and** the class
name. I re-ran my rc1 mutation 3 (an impostor class named `LlmAgent` defined in
`app.organizer`) — the exact attack that defeated rc1:

```
CAUGHT: Eligibility drift detected: framework='LlmAgent'
```

Genuinely closed against realistic drift. Residual, for the record: a class that
deliberately sets `__module__ = 'google.adk.agents.llm_agent'` still passes —

```
get_config -> {'agent_type': 'LlmAgent', ..., 'framework': 'Google ADK'}
```

— but that is sabotage, not drift. An `isinstance` against a freshly imported
`google.adk.agents.LlmAgent` would close it completely. Mutations reverted, tree
clean.

### Vertex validation — closed, fail-closed

`app/organizer.py:94-98`. Observed behaviour:

```
GOOGLE_GENAI_USE_VERTEXAI='true'   -> CONSTRUCTS
GOOGLE_GENAI_USE_VERTEXAI='TRUE'   -> refused
GOOGLE_GENAI_USE_VERTEXAI='True'   -> refused
GOOGLE_GENAI_USE_VERTEXAI='1'      -> refused
GOOGLE_GENAI_USE_VERTEXAI='false'  -> refused
GOOGLE_GENAI_USE_VERTEXAI=''       -> refused
GOOGLE_GENAI_USE_VERTEXAI=UNSET    -> refused
```

The rc1 hole is closed: the app can no longer boot onto the Gemini Developer API
while reporting `location: global`. Two notes, neither dangerous:

- It is stricter than the SDK, which accepts `"1"` and any case
  (`_api_client.py:662`). `GOOGLE_GENAI_USE_VERTEXAI=1` is a valid Vertex
  configuration that this app refuses to start on. Fail-closed direction, so
  safe.
- The check is skipped entirely when an `llm` is injected (`if llm is None and …`).
  That is how the offline tests construct agents; production (`app/chat.py:128`)
  never injects, so production is guarded.

---

## 5. What the repairs broke

### The README's own offline setup no longer starts the app

`README.md:27-32` is the documented way to run locally. Executed verbatim:

```
RuntimeError: Agent initialization failed: GOOGLE_GENAI_USE_VERTEXAI must be
set to 'true' for contest eligibility, got None
    server.py:26 -> app/chat.py:133
```

The service never listens. The new eligibility check was added without updating
the two commands the README gives for offline use — while the *browser-suite*
server command in the same file was updated with the variable.

### The offline suite is now environment-dependent

```
$ ./.venv/bin/python -m pytest -q                              # clean shell
8 failed, 111 passed, 1 skipped

$ GOOGLE_GENAI_USE_VERTEXAI=true ./.venv/bin/python -m pytest -q
119 passed, 1 skipped
```

The eight failures are all `ValueError: GOOGLE_GENAI_USE_VERTEXAI must be set…`
from tests that construct a real agent: `test_chat_foundation.py` (×3),
`test_eligibility_guard.py::test_correct_config_succeeds`,
`test_foundation_complete.py` (×2), `test_foundation_simple.py::test_agent_config`,
`tests/test_knowledge_learning.py::test_card1_…`.

The reported `119 passed, 1 skipped` is reproducible, but only with that variable
exported. `README.md:39-43` does not set it. A reviewer following the README from
a clean shell sees eight failures.

### The demo script is broken

`docs/SHOT-LIST.md:13` — see §2, Regression B.

### What survived intact — all re-verified, not assumed

| Behaviour | Result |
|---|---|
| System prompt exactly 90 words | `words=90 chars=564` ✓ |
| Vague reply keeps default, no re-ask, no model call | `'Kept the default — tomorrow, Anywhere, 30 min.'`, no `?`, model not reached ✓ |
| At most one question per turn | `_at_most_one_question('a? b? c?') -> 'a?'` ✓ |
| Two plans genuinely differ | A=`['Deep proposal','Review notes','Quick email']`, B=`['Quick email','Deep proposal','Review notes']`, `similar=False` ✓ |
| Place filtering | Home and Done rows both excluded ✓ |
| Pick writes only `When` | only `when` changed; untouched rows kept `when=None` ✓ |
| Five-operation MCP allowlist | `create_page, set_page_title, set_page_property, query_database, archive_page` — unchanged ✓ |
| Single-chokepoint board gate | one wrap site (`app/organizer.py:218`), one definition (`:222`); `tests/test_automation_board_gate.py` → 5 passed ✓ |
| Row-aware isolation regression | `scripts/notion_board_setup.py` SHA-256 still `f1f2d990fad25852f2ab30726fadd85daadf47b5c511e250ddef4ddc0dcfde3a`; zero diff since rc1 across all Notion files ✓ |

Nothing was weakened to make anything pass.

---

## UNVERIFIED at rc2

- **Live Vertex and live Notion.** Prohibited and not attempted. No Notion read,
  write, query or count was issued. Avi's single board row was not touched.
- **Cloud Run deployment, the `/knowledge` Cloud Storage mount, the scheduler.**
  Nothing deployed.
- **Whether the browser checks after `ui_browser_suite.mjs:243` pass at rc2 as
  shipped.** Execution halts there. The clone experiment shows all nine pass once
  punctuation is tolerated, but that is a modified tree, not this tag.
- **Secret scan.** Not re-run at rc2. It passed cleanly at rc1, and the rc1→rc2
  diff touches only `README.md`, `app/chat.py`, `app/organizer.py`,
  `app/task_planning.py`, four docs/evidence files, two new test files and
  `web/favicon.ico` — none credential-bearing — but I did not re-measure.
- **Model behaviour on vague phrasings** outside the nine literals in `_VAGUE`.

---

## Smallest set of changes that would clear this

1. `app/organizer.py:314-320` — anchor `_is_asking_for_plan`, or require the
   plan/schedule verb to govern the whole message. Add a test for a *task*
   containing the word "plan" or "schedule".
2. `app/organizer.py:322-345` — tolerate trailing sentence punctuation before the
   anchored match. This alone turns the browser matrix green (proved: 9/9).
3. `README.md:27-32` and `:39-43` — add `GOOGLE_GENAI_USE_VERTEXAI=true`, or let
   the offline/fake path construct without it.
4. Withdraw the three 9/9 browser claims until a run at the tag produces one, and
   clear the now-stale `NEEDS CLOSURE` row in `evidence/fact-check-log.md`.

---

# rc1 — 2026-08-24 (condensed, superseded)

Judged commit `730d98fddbb0b7cbafb9347e695f6a02bc66142b`, tag
`avi-notes-assistant-rc1`. Verdict: **NO**.

- **Eligibility: PASS.** One ADK `LlmAgent` + one `Runner`; constructed client
  observed as `vertexai=true`, `location=global`,
  `base_url=https://aiplatform.googleapis.com/`, ADK `Gemini`,
  `gemini-3.5-flash`. Uses Vertex AI, Vertex embeddings and Firestore. Mutations:
  model → 9 failed, location → 11 failed, framework → 7 failed, all reverted.
  Framework drift was caught only collaterally; both dedicated eligibility tests
  passed while `get_config()` falsely reported `"Google ADK"`.
- **Blocker 1:** `extract_place` hijacked ordinary reminders —
  `"remind me to call the dentist tomorrow at 3pm"` created no row. 7 of 10
  realistic phrasings discarded.
- **Blocker 2:** browser suite failed deterministically on a missing
  `/favicon.ico`; adding one in a throwaway clone produced 9/9.
- **Six false/stale claims**, including evidence describing a failed
  orchestrator run as "eight passing checks".
- Board gate PASS (5 tests; fifth-tool auto-gating verified by adding one).
  Secrets clean: 0 exact-value hits across 17,139 worktree files, 82 tracked
  files, 490 git objects, 0 dangling. Clean checkout PASS on Python 3.14.6.
