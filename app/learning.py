"""Minimal Learning view and its aggregate-only browser contract."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from app.knowledge import OrganizerKnowledge


class DailySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    summary: str


class PeriodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_changes: int
    skills_created_updated: int
    rules_changed: int
    dreams_consolidated: int
    daily_summaries: list[DailySummaryResponse]
    window_start: str


class LearningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    week_start: int
    generated_at: str
    periods: dict[Literal["day", "week", "month"], PeriodResponse]


def create_learning_router(
    get_knowledge: Callable[[], OrganizerKnowledge],
    *,
    web_root: Path | str | None = None,
) -> APIRouter:
    """Create exactly one aggregate endpoint and one HTML view route."""

    router = APIRouter()
    resolved_web_root = Path(web_root) if web_root else Path(__file__).parent.parent / "web"

    @router.get("/learning", include_in_schema=False)
    def learning_view():
        page = resolved_web_root / "learning.html"
        if not page.exists():
            raise HTTPException(404, "Learning view is not installed")
        return FileResponse(page)

    @router.get("/api/learning", response_model=LearningResponse)
    def learning_aggregates(
        timezone: str = Query(..., min_length=1, max_length=80),
        week_start: int = Query(0, ge=0, le=6),
    ):
        try:
            return get_knowledge().learning_aggregates(
                timezone_name=timezone,
                week_start=week_start,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router
