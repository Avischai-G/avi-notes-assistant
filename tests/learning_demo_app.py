"""Local-only fixture app for rendered Learning-view and network inspection."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.knowledge import OrganizerKnowledge
from app.knowledge_index import LocalEmbeddingCache, SkillIndex
from app.knowledge_store import MarkdownKnowledgeStore
from app.learning import create_learning_router
from app.learning_store import LearningEvent, LocalLearningEventStore


UTC = timezone.utc
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
WEB = Path(__file__).parents[1] / "web"


class OfflineEmbeddings:
    model = "gemini-embedding-001"
    location = "global"

    def embed(self, text: str, *, task_type: str) -> list[float]:
        return [1.0, 0.0]


events = LocalLearningEventStore(
    [
        LearningEvent(
            datetime(2026, 8, 21, 21, 30, tzinfo=UTC),
            "skills/today.md",
            "created",
            "PRIVATE skill-event detail",
        ),
        LearningEvent(
            datetime(2026, 8, 15, 21, 30, tzinfo=UTC),
            "rules/week.md",
            "updated",
            "PRIVATE rule-event detail",
        ),
        LearningEvent(
            datetime(2026, 7, 31, 21, 30, tzinfo=UTC),
            "skills/month.md",
            "consolidated",
            "PRIVATE consolidation detail",
        ),
    ]
)
root = Path(tempfile.mkdtemp(prefix="coroner-learning-demo-"))
store = MarkdownKnowledgeStore(root, events, clock=lambda: NOW)
index = SkillIndex(root, OfflineEmbeddings(), LocalEmbeddingCache())
knowledge = OrganizerKnowledge(store, index, clock=lambda: NOW)

api = FastAPI(title="Learning view fixture")
api.include_router(create_learning_router(lambda: knowledge, web_root=WEB))
api.mount("/", StaticFiles(directory=WEB, html=True), name="web")
