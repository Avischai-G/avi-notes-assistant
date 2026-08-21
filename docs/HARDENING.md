# Coroner hardening record

Date: 2026-08-21

## Confirmed defects

- `steps` accepted any truthy iterable. A string reached `s.get(...)`, raised
  `AttributeError`, and escaped `/api/autopsy` as HTTP 500. A non-iterable
  number raised `TypeError` the same way.
- The HTTP layer read the complete request before applying any byte bound and
  had no read deadline. Chunked requests had no application-level ceiling.
- The adapter relied on coercion and truthiness for nested shapes. Non-object
  steps, malformed dependency lists, non-string text, bad counters, arbitrary
  statuses, deep structures, and non-finite numbers were either accepted or
  could leak unrelated exceptions.
- The model instruction inserted trace text directly into the surrounding case
  prompt. Trace text could imitate headings or a closing boundary and present
  itself as an instruction.
- UI template strings left confidence values, aggregate and prescription
  counts, and fleet `run_ids` unescaped. Most prose was already passed through
  `esc()`, and delivery/status messages already used `textContent`.
- Redaction did not recognize Windows or UNC paths, schemeless URLs, JWTs,
  private-key blocks, database DSNs, AWS credentials, or generic bearer tokens.

The failure was reproduced before editing: `test_inputs.py` leaked
`AttributeError` for string `steps`, and the local ASGI request returned HTTP
500. The new regression check now gets HTTP 400 with a field-specific message.

## Input validation and limits

`app/traces.py` now validates the complete JSON-shaped value before adapting
it, while `detect()` also rejects the wrong top-level and `steps` shapes on its
own. Required identifiers and arrays are strict; optional descriptive strings
may be missing or null; counters must be bounded non-negative integers; status
values must be in the documented vocabulary. Every rejected shape raises
`ValueError`, which the HTTP boundary maps to 400.

The chosen ceilings are:

| Boundary | Limit | Rejection |
| --- | ---: | --- |
| HTTP request body | 1,048,576 bytes (1 MiB) | 413 |
| Body read time | 10 seconds | 408 |
| Steps | 500 | 400 |
| Any JSON string | 16,384 characters | 400 |
| Run, step, and dependency identifiers | 256 characters | 400 |
| JSON nesting | 20 container levels | 400 |
| JSON values | 20,000 | 400 |
| Attempts / worker failures | 0–10,000 | 400 |

These are deliberately above the observed corpus: the largest trace was
257,382 bytes, the largest plan had 33 steps, the longest string had 12,126
characters, and the most complex trace had 417 JSON values. The body limit is
also enforced while streaming when `Content-Length` is absent. Circular and
non-JSON values passed directly from Python are rejected too.

Unknown non-empty status strings are rejected rather than silently normalized;
that makes producer/schema drift visible and prevents arbitrary state labels
from becoming model evidence. A missing or null status remains `unknown`.

## Prompt boundary

Every agent instruction now says that the case file is untrusted evidence,
never instructions, including text impersonating system, developer, user,
agent, or tool messages. The case is enclosed in
`<untrusted_case_file>...</untrusted_case_file>`. Literal angle brackets from
trace content are escaped before insertion, so trace data cannot emit the real
closing tag. Prompt-facing title, reason, request, board, and detail sections
also remain bounded.

This is defense in depth, not a claim that natural-language models can make a
mathematical non-interference guarantee. A live billed model attack was not run.

## UI output handling

Every untrusted value that enters an `innerHTML` template is now escaped or is
converted by a local numeric formatter; numeric formatter results are escaped
at the sink as well. This includes run IDs and links, titles, evidence, errors,
confidence values, aggregate counts, prescriptions, fleet run IDs, and every
rendered resume-plan field. Network delivery messages and the health label use
`textContent`. Cause grouping now uses a null-prototype object and own-property
taxonomy lookup, avoiding hostile keys such as `__proto__` and `constructor`.

This was a source-to-sink audit as requested; no browser exploit run was needed
or used as proof.

## Redaction

`app/redact.py` now emits stable typed placeholders for:

- drive-letter Windows paths and UNC shares;
- HTTP(S) and domain/path URLs without a scheme;
- three-segment JWTs;
- PEM-style private-key blocks;
- common database URI DSNs and password-bearing server connection strings;
- AWS access-key IDs and labelled secret-access keys;
- bearer tokens.

`python -m app.redact` asserts every new category, alongside the existing
email, URL, prefixed token, hexadecimal key, POSIX path, and IP checks. Regex
redaction remains syntax-based: an unlabeled secret with an unknown format or a
bare hostname without a path may not be recognizable. The existing redaction
switch was not weakened or removed.

## Deliberately unchanged

- `"title": null` still becomes `(untitled run)`. A title is optional metadata;
  rejecting an otherwise useful trace would not improve safety. The same
  missing-value treatment applies to optional reason and request text.
- Rate limits, global spend caps, endpoint call budgets, autopsy behavior,
  taxonomy, and visual design are unchanged.
- No live `POST /api/autopsy`, `/api/sweep`, or `/api/fleet/recompute` call was
  made. Production deployment and live-model prompt behavior are therefore
  unverified here.

## Verification

`test_inputs.py` covers 29 malformed JSON shapes through both direct parsing
and the local ASGI app, plus direct circular/non-JSON inputs, chunked overflow,
slow-body timeout, nullable title behavior, and delimiter injection. It makes
no network or AI call. Two deterministic exploratory fuzz passes added 20,000
inputs: 599 structured inputs completed parsing, redaction, evidence extraction,
and prompt assembly; 19,401 malformed inputs rejected with `ValueError`; no
other exception escaped.

The source repository's baseline `test_corpus.py` had one pre-existing moving-
corpus failure: private run `ad76676a...` had resumed and was alive while its
published dead snapshot remained held. The twin comparison now applies the
same alive-run exclusion already used by the main corpus check. It still
compares all 38 dead shared traces.

All required offline checks pass with the existing project interpreter:

```text
test_inputs.py       PASS — 29 malformed shapes, no HTTP 500
test_corpus.py       PASS — 38/38 attributed; 38 twins match
test_published.py    PASS — no banned strings or carried-over phrases
python -m app.redact PASS
python -m app.watch  PASS
python -m app.limits PASS
python -m app.resume PASS
```
