"""Small-corpus semantic skill index ranked locally by cosine similarity."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Protocol, Sequence


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_LOCATION = "global"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class EmbeddingClient(Protocol):
    model: str
    location: str

    def embed(self, text: str, *, task_type: str) -> list[float]: ...


class VertexEmbeddingClient:
    """Google Gen AI SDK adapter fixed to Vertex global and Gemini embeddings."""

    model = EMBEDDING_MODEL
    location = EMBEDDING_LOCATION

    def __init__(self, project: str | None, client=None) -> None:
        self.project = project
        self._client = client

    def _get_client(self):
        if self._client is None:
            if not self.project:
                raise RuntimeError(
                    "GOOGLE_CLOUD_PROJECT is required to embed knowledge with Vertex AI"
                )
            from google import genai

            self._client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
            )
        return self._client

    def embed(self, text: str, *, task_type: str) -> list[float]:
        from google.genai.types import EmbedContentConfig

        response = self._get_client().models.embed_content(
            model=self.model,
            contents=text,
            config=EmbedContentConfig(task_type=task_type),
        )
        if not response.embeddings or not response.embeddings[0].values:
            raise RuntimeError("Vertex returned no embedding values")
        return [float(value) for value in response.embeddings[0].values]


@dataclass(frozen=True)
class SkillEmbedding:
    path: str
    content_hash: str
    vector: tuple[float, ...]
    model: str = EMBEDDING_MODEL
    location: str = EMBEDDING_LOCATION

    def to_firestore(self) -> dict:
        return {
            "path": self.path,
            "content_hash": self.content_hash,
            "vector": list(self.vector),
            "model": self.model,
            "location": self.location,
        }

    @classmethod
    def from_firestore(cls, value: dict) -> "SkillEmbedding":
        return cls(
            path=str(value["path"]),
            content_hash=str(value["content_hash"]),
            vector=tuple(float(item) for item in value["vector"]),
            model=str(value.get("model", EMBEDDING_MODEL)),
            location=str(value.get("location", EMBEDDING_LOCATION)),
        )


class EmbeddingCache(Protocol):
    def get(self, path: str) -> SkillEmbedding | None: ...

    def put(self, embedding: SkillEmbedding) -> None: ...


class LocalEmbeddingCache:
    def __init__(self) -> None:
        self.records: dict[str, SkillEmbedding] = {}

    def get(self, path: str) -> SkillEmbedding | None:
        return self.records.get(path)

    def put(self, embedding: SkillEmbedding) -> None:
        self.records[embedding.path] = embedding


class FirestoreEmbeddingCache:
    """Cache path, SHA-256 content hash, and vector in Firestore."""

    COLLECTION = "knowledge_skill_embeddings"

    def __init__(self, db, collection: str = COLLECTION) -> None:
        self._collection = db.collection(collection)

    @staticmethod
    def _document_id(path: str) -> str:
        return hashlib.sha256(path.encode("utf-8")).hexdigest()

    def get(self, path: str) -> SkillEmbedding | None:
        snapshot = self._collection.document(self._document_id(path)).get()
        if not snapshot.exists:
            return None
        return SkillEmbedding.from_firestore(snapshot.to_dict())

    def put(self, embedding: SkillEmbedding) -> None:
        self._collection.document(self._document_id(embedding.path)).set(
            embedding.to_firestore()
        )


@dataclass(frozen=True)
class RankedSkill:
    path: str
    content: str
    score: float


class SkillIndex:
    """Embed changed documents, then rank the complete small corpus in Python."""

    def __init__(
        self,
        root: Path | str,
        embeddings: EmbeddingClient,
        cache: EmbeddingCache,
    ) -> None:
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.embeddings = embeddings
        self.cache = cache

    def _document_vector(self, path: Path, content: str) -> tuple[float, ...]:
        logical_path = path.relative_to(self.root).as_posix()
        digest = content_hash(content)
        cached = self.cache.get(logical_path)
        if (
            cached is not None
            and cached.content_hash == digest
            and cached.model == self.embeddings.model
            and cached.location == self.embeddings.location
        ):
            return cached.vector

        vector = tuple(
            float(value)
            for value in self.embeddings.embed(
                content,
                task_type="RETRIEVAL_DOCUMENT",
            )
        )
        self.cache.put(
            SkillEmbedding(
                path=logical_path,
                content_hash=digest,
                vector=vector,
                model=self.embeddings.model,
                location=self.embeddings.location,
            )
        )
        return vector

    def rank(self, query: str, limit: int = 3) -> list[RankedSkill]:
        if limit < 0:
            raise ValueError("rank limit must not be negative")
        paths = sorted(self.skills_dir.glob("*.md"))
        if not paths or limit == 0:
            return []
        if not query.strip():
            query = "organize the current task"
        query_vector = self.embeddings.embed(query, task_type="RETRIEVAL_QUERY")
        ranked: list[RankedSkill] = []
        for path in paths:
            content = path.read_text(encoding="utf-8")
            vector = self._document_vector(path, content)
            ranked.append(
                RankedSkill(
                    path=path.relative_to(self.root).as_posix(),
                    content=content,
                    score=cosine_similarity(query_vector, vector),
                )
            )
        ranked.sort(key=lambda skill: (-skill.score, skill.path))
        return ranked[:limit]
