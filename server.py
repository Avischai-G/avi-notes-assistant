"""Avi's notes assistant as a small FastAPI service."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import chat


WEB = Path(__file__).parent / "web"

api = FastAPI(
    title="Avi's Notes Assistant",
    description="A concise chat assistant that organises one scoped Notion board.",
)

# Local development is deterministic and offline by default. Cloud Run is durable
# and fail-closed: Firestore and the scoped Notion configuration must both resolve.
use_firestore = os.environ.get(
    "USE_FIRESTORE", "1" if os.environ.get("K_SERVICE") else "0"
) != "0"
chat.init_chat_stores(use_firestore=use_firestore)

chat.register_chat_routes(api)


@api.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html")


# API and /learning routes are registered first, so this final mount serves only
# the no-build browser assets and never shadows application endpoints.
api.mount("/", StaticFiles(directory=WEB), name="web")
