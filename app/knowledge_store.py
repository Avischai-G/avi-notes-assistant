"""UTF-8 Markdown knowledge store with strict paths and write provenance."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import tempfile

from app.learning_store import LearningEvent, LearningEventStore, utc_now


MAX_SKILL_WORDS = 499
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
_RULE_MARKER = "<!-- agentonomy: explicit-user-instruction -->"
# Rules written before the rename carry the old marker; keep reading them.
_LEGACY_RULE_MARKER = "<!-- agentonomy: explicit-avi-instruction -->"
_INCORPORATED_HEADING = "## Incorporated dream notes"


class KnowledgeValidationError(ValueError):
    pass


class SkillTooLongError(KnowledgeValidationError):
    pass


def count_words(content: str) -> int:
    """Count whitespace-delimited Markdown words for the 500-word hard boundary."""

    return len(re.findall(r"\S+", content))


def _validated_text(content: str, label: str) -> str:
    if not isinstance(content, str):
        raise KnowledgeValidationError(f"{label} must be text")
    content = content.strip()
    if not content:
        raise KnowledgeValidationError(f"{label} must not be empty")
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise KnowledgeValidationError(f"{label} must be valid UTF-8") from exc
    if "\x00" in content:
        raise KnowledgeValidationError(f"{label} must not contain NUL bytes")
    return content + "\n"


def _validated_slug(name: str) -> str:
    if not isinstance(name, str) or not _SLUG.fullmatch(name):
        raise KnowledgeValidationError(
            "knowledge names must be lowercase letters, digits, hyphens, or underscores"
        )
    return name


class MarkdownKnowledgeStore:
    """Own the exact ``skills/``, ``rules/``, and ``dreams/`` layout."""

    def __init__(self, root: Path | str, events: LearningEventStore, clock=utc_now) -> None:
        self.root = Path(root)
        self.events = events
        self.clock = clock
        self.skills_dir = self.root / "skills"
        self.rules_dir = self.root / "rules"
        self.dreams_dir = self.root / "dreams"
        for directory in (self.skills_dir, self.rules_dir, self.dreams_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _write_and_record(
        self,
        path: Path,
        content: str,
        *,
        action: str,
        summary: str,
        timestamp: datetime | None = None,
        require_absent: bool = False,
    ) -> Path:
        existed = path.exists()
        if require_absent and existed:
            raise FileExistsError(path)
        previous = path.read_text(encoding="utf-8") if existed else None
        self._atomic_write(path, content)
        try:
            self.events.append(
                LearningEvent(
                    timestamp=timestamp or self.clock(),
                    path=self.logical_path(path),
                    action=action,
                    summary=summary,
                )
            )
        except Exception:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                self._atomic_write(path, previous)
            raise
        return path

    def logical_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise KnowledgeValidationError("path escapes the knowledge root") from exc

    def skill_path(self, name: str) -> Path:
        return self.skills_dir / f"{_validated_slug(name)}.md"

    def rule_path(self, name: str) -> Path:
        return self.rules_dir / f"{_validated_slug(name)}.md"

    def write_skill(
        self,
        name: str,
        content: str,
        *,
        summary: str,
        timestamp: datetime | None = None,
    ) -> Path:
        path = self.skill_path(name)
        body = _validated_text(content, "skill")
        words = count_words(body)
        if words > MAX_SKILL_WORDS:
            raise SkillTooLongError(
                f"skills must contain fewer than 500 words; received {words}"
            )
        action = "updated" if path.exists() else "created"
        return self._write_and_record(
            path,
            body,
            action=action,
            summary=summary,
            timestamp=timestamp,
        )

    def write_rule(
        self,
        name: str,
        content: str,
        *,
        explicit_user_instruction: bool,
        summary: str,
        timestamp: datetime | None = None,
    ) -> Path:
        if explicit_user_instruction is not True:
            raise KnowledgeValidationError(
                "a rule requires an explicit user instruction; observations belong in dreams"
            )
        path = self.rule_path(name)
        rule = _validated_text(content, "rule")
        body = f"{_RULE_MARKER}\n\n{rule}"
        action = "updated" if path.exists() else "created"
        return self._write_and_record(
            path,
            body,
            action=action,
            summary=summary,
            timestamp=timestamp,
        )

    def append_dream(
        self,
        target_skill: str,
        observation: str,
        *,
        summary: str,
        timestamp: datetime | None = None,
    ) -> Path:
        name = _validated_slug(target_skill)
        body = _validated_text(observation, "dream observation")
        occurred_at = timestamp or self.clock()
        epoch = int(occurred_at.timestamp() * 1000)
        path = self.dreams_dir / f"skills__{name}.md.{epoch}.md"
        while path.exists():
            epoch += 1
            path = self.dreams_dir / f"skills__{name}.md.{epoch}.md"
        return self._write_and_record(
            path,
            body,
            action="dreamed",
            summary=summary,
            timestamp=occurred_at,
            require_absent=True,
        )

    def read_skill(self, name: str) -> str:
        return self.skill_path(name).read_text(encoding="utf-8")

    def read_rule(self, name: str) -> str:
        body = self.rule_path(name).read_text(encoding="utf-8")
        for marker in (_RULE_MARKER, _LEGACY_RULE_MARKER):
            if body.startswith(marker):
                return body[len(marker) :].strip() + "\n"
        raise KnowledgeValidationError(
            f"rules/{name}.md has no explicit-instruction provenance marker"
        )

    def list_skill_paths(self) -> list[Path]:
        return sorted(self.skills_dir.glob("*.md"))

    def list_rules(self) -> list[tuple[str, str]]:
        rules: list[tuple[str, str]] = []
        for path in sorted(self.rules_dir.glob("*.md")):
            body = path.read_text(encoding="utf-8")
            for marker in (_RULE_MARKER, _LEGACY_RULE_MARKER):
                if body.startswith(marker):
                    rules.append((self.logical_path(path), body[len(marker) :].strip()))
                    break
        return rules

    def list_dream_paths(self, target_skill: str) -> list[Path]:
        name = _validated_slug(target_skill)
        return sorted(self.dreams_dir.glob(f"skills__{name}.md.*.md"))

    @staticmethod
    def _without_incorporated_trace(content: str) -> str:
        marker = f"\n\n{_INCORPORATED_HEADING}\n"
        return content.strip().rsplit(marker, 1)[0].strip()

    def consolidate_skill(
        self,
        target_skill: str,
        *,
        summary: str | None = None,
        timestamp: datetime | None = None,
    ) -> tuple[Path, list[str]]:
        """Rewrite exactly one skill, preserving every distinct dream observation."""

        name = _validated_slug(target_skill)
        notes = self.list_dream_paths(name)
        if not notes:
            raise KnowledgeValidationError(f"no dream notes exist for skill {name}")

        skill_path = self.skill_path(name)
        existing = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
        core = self._without_incorporated_trace(existing)
        normalized_core = " ".join(core.split())
        facts: list[str] = []
        seen: set[str] = set()
        for note in notes:
            fact = note.read_text(encoding="utf-8").strip()
            normalized = " ".join(fact.split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                if normalized not in normalized_core:
                    facts.append(fact)

        sections = [core] if core else [f"# {name.replace('-', ' ').title()}"]
        if facts:
            sections.append("## Learned observations\n\n" + "\n\n".join(facts))
        incorporated = [self.logical_path(note) for note in notes]
        trace = _INCORPORATED_HEADING + "\n\n" + "\n".join(
            f"- `{path}`" for path in incorporated
        )
        consolidated = "\n\n".join(section for section in sections if section) + "\n\n" + trace
        consolidated = _validated_text(consolidated, "consolidated skill")
        words = count_words(consolidated)
        if words > MAX_SKILL_WORDS:
            raise SkillTooLongError(
                f"consolidation would create {words} words; skill was left unchanged"
            )

        event_summary = summary or (
            f"Consolidated {len(notes)} dream note"
            f"{'s' if len(notes) != 1 else ''} into {name}."
        )
        self._write_and_record(
            skill_path,
            consolidated,
            action="consolidated",
            summary=event_summary,
            timestamp=timestamp,
        )
        return skill_path, incorporated
