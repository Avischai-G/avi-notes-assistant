"""Where case files live.

Firestore in production, a directory of JSON on a laptop. Same three calls
either way, so nothing upstream knows or cares which one is running.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

COLLECTION = "cases"
TRACES = "traces"        # raw traces the watcher sweeps
META = "meta"            # small singletons: last sweep, etc.
# The project's (default) database is in Datastore mode, which the Firestore
# API refuses to serve, so Coroner uses its own native-mode database.
DATABASE = os.environ.get("CORONER_FIRESTORE_DB", "coroner")
LOCAL = Path(os.environ.get("CORONER_LOCAL_STORE", "data/cases"))
_USE_FIRESTORE = os.environ.get("CORONER_STORE", "").lower() == "firestore"


def _db():
    from google.cloud import firestore
    return firestore.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"], database=DATABASE)


def save(case: dict) -> None:
    run_id = case["run_id"]
    if _USE_FIRESTORE:
        _db().collection(COLLECTION).document(run_id).set(case)
        return
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / f"{run_id}.json").write_text(json.dumps(case, indent=2))


def get(run_id: str) -> dict | None:
    if _USE_FIRESTORE:
        d = _db().collection(COLLECTION).document(run_id).get()
        return d.to_dict() if d.exists else None
    p = LOCAL / f"{run_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def all_cases() -> list[dict]:
    if _USE_FIRESTORE:
        return [d.to_dict() for d in _db().collection(COLLECTION).stream()]
    if not LOCAL.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(LOCAL.glob("*.json"))]


def case_ids() -> set[str]:
    if _USE_FIRESTORE:
        return {d.id for d in _db().collection(COLLECTION).list_documents()}
    return {p.stem for p in LOCAL.glob("*.json")} if LOCAL.exists() else set()


# --- the traces the watcher sweeps ---------------------------------------
TRACE_DIR = Path(os.environ.get("CORONER_TRACE_DIR", "data/demo-traces"))


def put_trace(run_id: str, raw: dict) -> None:
    if _USE_FIRESTORE:
        _db().collection(TRACES).document(run_id).set({"raw": json.dumps(raw)})
        return
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    (TRACE_DIR / f"{run_id}.json").write_text(json.dumps(raw, indent=2))


def all_traces() -> list[dict]:
    if _USE_FIRESTORE:
        return [json.loads(d.to_dict()["raw"]) for d in _db().collection(TRACES).stream()]
    if not TRACE_DIR.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(TRACE_DIR.glob("*.json"))]


# --- small singletons -----------------------------------------------------
def put_meta(key: str, value: dict) -> None:
    if _USE_FIRESTORE:
        _db().collection(META).document(key).set(value)
        return
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL.parent / f"meta-{key}.json").write_text(json.dumps(value, indent=2))


def get_meta(key: str) -> dict | None:
    if _USE_FIRESTORE:
        d = _db().collection(META).document(key).get()
        return d.to_dict() if d.exists else None
    p = LOCAL.parent / f"meta-{key}.json"
    return json.loads(p.read_text()) if p.exists() else None
