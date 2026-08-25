"""One organizer's knowledge actions, retrieval context, and private log tool."""
from __future__ import annotations

import os
from pathlib import Path
import re

from app.knowledge_index import (
    FirestoreEmbeddingCache,
    LocalEmbeddingCache,
    SkillIndex,
    VertexEmbeddingClient,
)
from app.knowledge_store import MarkdownKnowledgeStore
from app.learning_store import (
    FirestoreLearningEventStore,
    LocalLearningEventStore,
    aggregate_learning_periods,
    utc_now,
)


def knowledge_root(
    *,
    production: bool | None = None,
    local_root: Path | str | None = None,
) -> Path:
    if production is None:
        production = bool(os.environ.get("K_SERVICE")) or (
            os.environ.get("CORONER_ENV", "").lower() == "production"
        )
    if production:
        return Path("/knowledge")
    if local_root is not None:
        return Path(local_root)
    configured = os.environ.get("CORONER_KNOWLEDGE_ROOT")
    return Path(configured) if configured else Path.cwd() / ".knowledge"


class OrganizerKnowledge:
    """Knowledge operations performed by the existing task organizer itself."""

    def __init__(self, store: MarkdownKnowledgeStore, index: SkillIndex, clock=utc_now) -> None:
        self.store = store
        self.index = index
        self.clock = clock

    def instruction_context(self, query: str) -> str:
        sections: list[str] = []
        rules = self.store.list_rules()
        if rules:
            rule_text = "\n\n".join(
                f"Source: {path}\n{content}" for path, content in rules
            )
            sections.append(
                "The user's explicit rules (hard constraints; do not infer new rules):\n"
                + rule_text
            )

        ranked = self.index.rank(query, limit=3)
        if ranked:
            skill_text = "\n\n".join(
                f"Source: {skill.path}\n{skill.content.strip()}" for skill in ranked
            )
            sections.append("Relevant atomic skills:\n" + skill_text)

        if not sections:
            return ""
        return "\n\nKnowledge for this turn:\n\n" + "\n\n".join(sections)

    def create_skill(self, name: str, content: str, change_summary: str) -> str:
        return self.store.logical_path(
            self.store.write_skill(name, content, summary=change_summary)
        )

    def record_rule(
        self,
        name: str,
        content: str,
        change_summary: str,
        *,
        explicit_user_instruction: bool,
    ) -> str:
        return self.store.logical_path(
            self.store.write_rule(
                name,
                content,
                explicit_user_instruction=explicit_user_instruction,
                summary=change_summary,
            )
        )

    def dream_skill(self, name: str, observation: str, change_summary: str) -> str:
        return self.store.logical_path(
            self.store.append_dream(name, observation, summary=change_summary)
        )

    def consolidate_skill(self, name: str, change_summary: str | None = None) -> dict:
        path, incorporated = self.store.consolidate_skill(
            name,
            summary=change_summary,
        )
        return {
            "path": self.store.logical_path(path),
            "incorporated_notes": incorporated,
        }

    def get_learning_log(self) -> list[dict]:
        """In-process agent tool: return complete private learning-event payloads."""

        return [event.to_agent_payload() for event in self.store.events.list_all()]

    def pending_dream_targets(self) -> list[str]:
        """Return skills with dream notes not yet named in their consolidation trace."""
        pending: set[str] = set()
        pattern = re.compile(r"^skills__(?P<name>[a-z0-9_-]+)\.md\.\d+\.md$")
        for note in sorted(self.store.dreams_dir.glob("skills__*.md.*.md")):
            match = pattern.fullmatch(note.name)
            if match is None:
                continue
            target = match.group("name")
            skill_path = self.store.skill_path(target)
            skill = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
            logical_note = self.store.logical_path(note)
            if f"`{logical_note}`" not in skill:
                pending.add(target)
        return sorted(pending)

    def has_dreams(self) -> bool:
        """Whether Knowledge cleanup has any unincorporated work."""
        return bool(self.pending_dream_targets())

    def consolidate(self) -> dict:
        """Consolidate every currently pending target exactly once."""
        targets = self.pending_dream_targets()
        if not targets:
            raise RuntimeError("no unincorporated dream notes")
        results = [self.consolidate_skill(target) for target in targets]
        return {
            "summary": (
                f"Consolidated {len(results)} skill"
                f"{'s' if len(results) != 1 else ''}."
            ),
            "skills": results,
            "learning_event": True,
        }

    def learning_aggregates(
        self,
        *,
        timezone_name: str,
        week_start: int,
    ) -> dict:
        snapshot = self.store.events.list_all()
        return aggregate_learning_periods(
            snapshot,
            now=self.clock(),
            timezone_name=timezone_name,
            week_start=week_start,
        )


def build_organizer_knowledge(
    *,
    db=None,
    root: Path | str | None = None,
    production: bool | None = None,
    embedding_client=None,
    clock=utc_now,
) -> OrganizerKnowledge:
    resolved_root = Path(root) if root is not None else knowledge_root(production=production)
    if db is None:
        events = LocalLearningEventStore()
        cache = LocalEmbeddingCache()
    else:
        events = FirestoreLearningEventStore(db)
        cache = FirestoreEmbeddingCache(db)
    embeddings = embedding_client or VertexEmbeddingClient(
        project=os.environ.get("GOOGLE_CLOUD_PROJECT")
    )
    store = MarkdownKnowledgeStore(resolved_root, events, clock=clock)
    index = SkillIndex(resolved_root, embeddings, cache)
    return OrganizerKnowledge(store, index, clock=clock)
