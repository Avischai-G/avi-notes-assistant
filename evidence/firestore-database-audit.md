# Firestore database-selection audit — 2026-08-24

## Authority and observed target state

Avi/Main Orchestrator established that project `gen-lang-client-0256233370`
already contains `(default)` in Datastore Mode and `coroner` in Firestore Native
mode. Avi authorized a configuration-only fix: `FIRESTORE_DATABASE`, defaulting
to `coroner`, passed to every Firestore client constructor. No cloud resource
creation or mutation was authorized or performed.

## Constructor search

The final source-tree audit searched Python files for `firestore.Client`,
`firestore.AsyncClient`, `firestore_v1`, Google Cloud Firestore imports, and all
generic `Client(` / `AsyncClient(` call sites, excluding dependency trees, git
objects, and the separate clean-checkout evidence clone.

Exactly one Firestore client construction exists:

- `app/chat.py` `_create_firestore_client()`.

`app/knowledge.py:179` constructs `VertexEmbeddingClient`, not a Firestore
client. `FirestoreLearningEventStore` and `FirestoreEmbeddingCache` receive the
single shared database client created by `app/chat.py`; they do not construct
another client.

## Implemented boundary

- Missing `FIRESTORE_DATABASE` selects `coroner`.
- A non-empty override is passed unchanged as `database=`.
- A blank value raises `RuntimeError` before client construction.
- Firestore client exceptions propagate; there is no local-store fallback.

`tests/test_firestore_database_config.py` mechanically asserts all four cases.

## Live result

With `FIRESTORE_DATABASE=coroner`, the approved acceptance service reached
`Application startup complete` and served the task, planner, Learning, and first
Knowledge requests. No composite-index error or other resource requirement
appeared. The later failure was an unexpected Knowledge-cleanup task-tool call,
not Firestore database selection.
