"""Where case files live.

Firestore in production, a directory of JSON on a laptop. Same three calls
either way, so nothing upstream knows or cares which one is running.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

COLLECTION = "cases"
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
