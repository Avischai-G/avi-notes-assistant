from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app.channel_store import LocalChannelStore
from app.knowledge import OrganizerKnowledge, knowledge_root
from app.knowledge_index import (
    EMBEDDING_LOCATION,
    EMBEDDING_MODEL,
    FirestoreEmbeddingCache,
    LocalEmbeddingCache,
    SkillEmbedding,
    SkillIndex,
    content_hash,
)
from app.knowledge_store import (
    KnowledgeValidationError,
    MarkdownKnowledgeStore,
    SkillTooLongError,
    count_words,
)
from app.learning import create_learning_router
from app.learning_store import (
    FirestoreLearningEventStore,
    LearningEvent,
    LocalLearningEventStore,
    aggregate_learning_periods,
)
from app.organizer import TaskOrganizerAgent
from app.task_store import FakeTaskStore


UTC = timezone.utc
FIXED_NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


class DeterministicEmbeddings:
    model = EMBEDDING_MODEL
    location = EMBEDDING_LOCATION

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def embed(self, text: str, *, task_type: str) -> list[float]:
        normalized = " ".join(text.lower().split())
        self.calls.append((normalized, task_type))
        if task_type == "RETRIEVAL_QUERY":
            return [1.0, 0.0, 0.0]
        if "calendar" in normalized or "planning" in normalized:
            return [1.0, 0.0, 0.0]
        if "breakdown" in normalized:
            return [0.8, 0.2, 0.0]
        if "communication" in normalized:
            return [0.0, 1.0, 0.0]
        if "recipe" in normalized:
            return [-1.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0]


def make_knowledge(tmp_path: Path, *, events=None, clock=lambda: FIXED_NOW):
    event_store = events or LocalLearningEventStore()
    store = MarkdownKnowledgeStore(tmp_path / "knowledge", event_store, clock=clock)
    embeddings = DeterministicEmbeddings()
    cache = LocalEmbeddingCache()
    index = SkillIndex(store.root, embeddings, cache)
    return OrganizerKnowledge(store, index, clock=clock), embeddings, cache


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_markdown_layout_utf8_word_boundary_and_rule_provenance(tmp_path: Path):
    events = LocalLearningEventStore()
    store = MarkdownKnowledgeStore(tmp_path / "knowledge", events, clock=lambda: FIXED_NOW)

    accepted = " ".join(f"word{i}" for i in range(499))
    skill_path = store.write_skill("atomic-howto", accepted, summary="Created the skill.")
    assert skill_path == tmp_path / "knowledge" / "skills" / "atomic-howto.md"
    assert skill_path.read_bytes().decode("utf-8").split() == accepted.split()
    assert count_words(skill_path.read_text(encoding="utf-8")) == 499

    rejected = " ".join(f"word{i}" for i in range(500))
    with pytest.raises(SkillTooLongError, match="fewer than 500 words"):
        store.write_skill("too-long", rejected, summary="Must not be written.")
    assert not (store.skills_dir / "too-long.md").exists()

    with pytest.raises(KnowledgeValidationError, match="explicit Avi instruction"):
        store.write_rule(
            "invented-rule",
            "An observation is not a rule.",
            explicit_avi_instruction=False,
            summary="Must not be written.",
        )
    assert list(store.rules_dir.glob("*.md")) == []

    rule_path = store.write_rule(
        "avi-language",
        "Avi explicitly said: תמיד שמור על ניסוח קצר.",
        explicit_avi_instruction=True,
        summary="Recorded Avi's language rule.",
    )
    assert rule_path == tmp_path / "knowledge" / "rules" / "avi-language.md"
    assert "תמיד" in rule_path.read_bytes().decode("utf-8")
    assert "תמיד" in store.read_rule("avi-language")

    dream_path = store.append_dream(
        "atomic-howto",
        "A concise example made the procedure clearer.",
        summary="Captured a clarity observation.",
        timestamp=datetime(2026, 8, 22, 8, 30, tzinfo=UTC),
    )
    assert dream_path.relative_to(store.root).as_posix() == (
        "dreams/skills__atomic-howto.md.1787387400000.md"
    )
    assert dream_path.read_text(encoding="utf-8").strip().endswith("clearer.")
    assert sorted(event.action for event in events.list_all()) == [
        "created",
        "created",
        "dreamed",
    ]


def test_event_failure_rolls_back_markdown_write(tmp_path: Path):
    class BrokenEvents:
        def append(self, event):
            raise RuntimeError("metadata unavailable")

        def list_all(self):
            return []

    store = MarkdownKnowledgeStore(tmp_path / "knowledge", BrokenEvents())
    with pytest.raises(RuntimeError, match="metadata unavailable"):
        store.write_skill("rollback", "This must be rolled back.", summary="Create.")
    assert not store.skill_path("rollback").exists()


def test_semantic_ranking_and_content_hash_cache_invalidation(tmp_path: Path):
    knowledge, embeddings, cache = make_knowledge(tmp_path)
    knowledge.create_skill("calendar", "Calendar planning procedure.", "Created calendar.")
    knowledge.create_skill("projects", "Project breakdown procedure.", "Created projects.")
    knowledge.create_skill("communication", "Communication procedure.", "Created comms.")
    knowledge.create_skill("recipes", "Recipe procedure.", "Created recipes.")

    ranked = knowledge.index.rank("Plan my week", limit=3)
    assert [item.path for item in ranked] == [
        "skills/calendar.md",
        "skills/projects.md",
        "skills/communication.md",
    ]
    assert len(embeddings.calls) == 5  # one query plus four first-time documents

    cached = cache.get("skills/calendar.md")
    assert cached is not None
    assert cached.path == "skills/calendar.md"
    assert cached.content_hash == content_hash("Calendar planning procedure.\n")
    assert cached.vector == (1.0, 0.0, 0.0)
    assert cached.model == "gemini-embedding-001"
    assert cached.location == "global"

    knowledge.index.rank("Plan my week", limit=3)
    assert len(embeddings.calls) == 6  # only the new query embedding

    knowledge.create_skill(
        "calendar",
        "Communication replaces the old calendar procedure.",
        "Updated calendar.",
    )
    knowledge.index.rank("Plan my week", limit=3)
    assert len(embeddings.calls) == 8  # query plus changed document only
    assert cache.get("skills/calendar.md").content_hash == content_hash(
        "Communication replaces the old calendar procedure.\n"
    )


def test_three_dream_facts_consolidate_without_touching_unrelated_files(tmp_path: Path):
    knowledge, _, _ = make_knowledge(tmp_path)
    store = knowledge.store
    target = store.write_skill(
        "daily-planning",
        "# Daily planning\n\nStart from the user's stated outcome.",
        summary="Created planning skill.",
    )
    unrelated = store.write_skill(
        "email",
        "# Email\n\nUse clear subject lines.",
        summary="Created email skill.",
    )
    rule = store.write_rule(
        "explicit-only",
        "Only Avi's explicit constraints are rules.",
        explicit_avi_instruction=True,
        summary="Recorded Avi's rule.",
    )
    unrelated_before = sha(unrelated)
    rule_before = sha(rule)

    facts = [
        "Put the user's deadline beside the task.",
        "Separate a blocked task from a merely low-priority task.",
        "End the plan with one concrete next action.",
    ]
    note_paths = []
    for index, fact in enumerate(facts):
        note_paths.append(
            store.append_dream(
                "daily-planning",
                fact,
                summary=f"Captured fact {index + 1}.",
                timestamp=datetime(2026, 8, 20, 9, index, tzinfo=UTC),
            )
        )

    consolidated_path, incorporated = store.consolidate_skill(
        "daily-planning",
        summary="Consolidated three planning observations.",
        timestamp=FIXED_NOW,
    )
    assert consolidated_path == target
    result = consolidated_path.read_text(encoding="utf-8")
    assert all(fact in result for fact in facts)
    assert incorporated == [store.logical_path(path) for path in note_paths]
    assert all(f"`{path}`" in result for path in incorporated)
    assert count_words(result) < 500
    assert sha(unrelated) == unrelated_before
    assert sha(rule) == rule_before
    assert list(store.rules_dir.glob("*.md")) == [rule]
    assert store.list_dream_paths("daily-planning") == note_paths
    assert store.events.list_all()[-1].action == "consolidated"


def boundary_events() -> list[LearningEvent]:
    return [
        # 00:30 on Aug 22 in Jerusalem, but Aug 21 in UTC.
        LearningEvent(
            datetime(2026, 8, 21, 21, 30, tzinfo=UTC),
            "skills/today.md",
            "created",
            "RAW skill body summary A",
        ),
        # Sunday Aug 16 in Jerusalem: inside the locale week.
        LearningEvent(
            datetime(2026, 8, 15, 21, 30, tzinfo=UTC),
            "rules/week.md",
            "updated",
            "RAW rule body summary B",
        ),
        # Aug 1 in Jerusalem, but July 31 in UTC.
        LearningEvent(
            datetime(2026, 7, 31, 21, 30, tzinfo=UTC),
            "skills/month.md",
            "consolidated",
            "RAW dream body summary C",
        ),
        LearningEvent(
            datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
            "dreams/skills__old.md.1.md",
            "dreamed",
            "RAW old body summary D",
        ),
    ]


def test_calendar_buckets_are_independent_timezone_local_and_non_mutating():
    store = LocalLearningEventStore(boundary_events())
    before = store.list_all()
    jerusalem = aggregate_learning_periods(
        before,
        now=FIXED_NOW,
        timezone_name="Asia/Jerusalem",
        week_start=0,  # Israel is still Sunday-first.
    )
    assert jerusalem["week_start"] == 6
    assert [
        jerusalem["periods"][period]["total_changes"]
        for period in ("day", "week", "month")
    ] == [1, 2, 3]
    assert jerusalem["periods"]["day"]["skills_created_updated"] == 1
    assert jerusalem["periods"]["week"]["rules_changed"] == 1
    assert jerusalem["periods"]["month"]["dreams_consolidated"] == 1

    utc = aggregate_learning_periods(
        store.list_all(),
        now=FIXED_NOW,
        timezone_name="UTC",
        week_start=0,
    )
    assert [
        utc["periods"][period]["total_changes"]
        for period in ("day", "week", "month")
    ] == [0, 1, 2]
    assert store.list_all() == before


class FakeDocumentSnapshot:
    def __init__(self, value=None):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return self.value


class FakeDocument:
    def __init__(self, collection, key):
        self.collection = collection
        self.key = key

    def get(self):
        return FakeDocumentSnapshot(self.collection.documents.get(self.key))

    def set(self, value):
        self.collection.documents[self.key] = value


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.added = []

    def document(self, key):
        return FakeDocument(self, key)

    def add(self, value):
        self.added.append(value)

    def stream(self):
        return [FakeDocumentSnapshot(value) for value in self.added]


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


def test_firestore_metadata_shapes_cache_and_private_events_only():
    db = FakeFirestore()
    cache = FirestoreEmbeddingCache(db)
    record = SkillEmbedding(
        path="skills/example.md",
        content_hash="abc123",
        vector=(0.1, 0.2),
    )
    cache.put(record)
    assert cache.get("skills/example.md") == record
    stored_cache = next(iter(db.collections[cache.COLLECTION].documents.values()))
    assert stored_cache == {
        "path": "skills/example.md",
        "content_hash": "abc123",
        "vector": [0.1, 0.2],
        "model": "gemini-embedding-001",
        "location": "global",
    }

    events = FirestoreLearningEventStore(db)
    event = boundary_events()[0]
    events.append(event)
    stored_event = db.collections[events.COLLECTION].added[0]
    assert set(stored_event) == {"timestamp", "path", "action", "summary"}
    assert events.list_all() == [event]


def test_aggregate_api_has_no_raw_event_payload_but_agent_tool_does(tmp_path: Path):
    event_store = LocalLearningEventStore(boundary_events())
    knowledge, _, _ = make_knowledge(tmp_path, events=event_store)
    app = FastAPI()
    router = create_learning_router(
        lambda: knowledge,
        web_root=Path(__file__).parents[1] / "web",
    )
    app.include_router(router)
    client = TestClient(app)

    response = client.get(
        "/api/learning",
        params={"timezone": "Asia/Jerusalem", "week_start": 0},
    )
    assert response.status_code == 200
    payload = response.json()
    serialized = response.text
    assert set(payload) == {"timezone", "week_start", "generated_at", "periods"}
    assert set(payload["periods"]) == {"day", "week", "month"}
    assert '"events"' not in serialized
    assert '"path"' not in serialized
    assert "RAW skill body summary A" not in serialized

    public_learning_routes = {
        route.path
        for route in router.routes
        if getattr(route, "path", "").startswith("/api/learning")
    }
    assert public_learning_routes == {"/api/learning"}
    assert client.get("/api/learning/events").status_code == 404
    assert client.get("/api/learning/log").status_code == 404
    assert client.get("/learning").status_code == 200

    full_log = knowledge.get_learning_log()
    assert any(item["path"] == "skills/month.md" for item in full_log)
    assert any(item["summary"] == "RAW skill body summary A" for item in full_log)


def test_single_instruction_contains_all_rules_and_only_top_three_skills(tmp_path: Path):
    knowledge, _, _ = make_knowledge(tmp_path)
    knowledge.record_rule(
        "first",
        "Always keep Avi's explicit deadline.",
        "Recorded first rule.",
        explicit_avi_instruction=True,
    )
    knowledge.record_rule(
        "second",
        "Never turn an observation into a rule.",
        "Recorded second rule.",
        explicit_avi_instruction=True,
    )
    knowledge.create_skill("calendar", "Calendar planning procedure.", "Created calendar.")
    knowledge.create_skill("projects", "Project breakdown procedure.", "Created projects.")
    knowledge.create_skill(
        "communication", "Communication procedure.", "Created communication."
    )
    knowledge.create_skill("recipes", "Recipe procedure.", "Created recipes.")

    class CapturingLlm(BaseLlm):
        _requests: list[LlmRequest] = PrivateAttr(default_factory=list)

        @property
        def requests(self):
            return self._requests

        async def generate_content_async(self, llm_request, stream=False):
            del stream
            self._requests.append(llm_request)
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text="Organized.")]
                )
            )

    model = CapturingLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(
        api_key="test-key", knowledge=knowledge, llm=model
    )
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    tasks = FakeTaskStore()

    async def collect():
        return [
            chunk
            async for chunk in agent.chat(
                "Plan my week",
                channel_store=channels,
                task_store=tasks,
                channel_id=channel_id,
            )
        ]

    chunks = asyncio.run(collect())
    assert chunks == [{"text": "Organized."}, {"done": True}]
    assert len(model.requests) == 1
    request = model.requests[0]
    instruction = request.config.system_instruction
    assert isinstance(instruction, str)
    assert instruction.count("Knowledge for this turn:") == 1
    assert "rules/first.md" in instruction and "rules/second.md" in instruction
    assert "skills/calendar.md" in instruction
    assert "skills/projects.md" in instruction
    assert "skills/communication.md" in instruction
    assert "skills/recipes.md" not in instruction
    assert all(
        message.role not in {"system", "developer"}
        for message in request.contents
    )
    assert agent.get_config()["model"] == "gemini-3.5-flash"
    assert agent.get_config()["location"] == "global"
    assert agent.get_learning_log()[-1]["path"] == "skills/recipes.md"


def test_production_mount_is_exact_and_local_root_is_explicit(tmp_path: Path):
    assert knowledge_root(production=True) == Path("/knowledge")
    assert knowledge_root(production=False, local_root=tmp_path) == tmp_path


def test_card1_chat_router_wires_learning_without_changing_chat_contract(
    tmp_path: Path, monkeypatch
):
    from app import chat

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path / "local-knowledge"))
    stores = chat.init_chat_stores(use_firestore=False)
    assert len(stores) == 3  # Card 1's frozen return contract remains unchanged.

    app = FastAPI()
    chat.register_chat_routes(app)
    client = TestClient(app)
    response = client.get(
        "/api/learning",
        params={"timezone": "Asia/Jerusalem", "week_start": 6},
    )
    assert response.status_code == 200
    assert response.json()["periods"]["day"]["total_changes"] == 0
    assert client.get("/api/learning/log").status_code == 404
    assert client.get("/api/tasks").status_code == 404
