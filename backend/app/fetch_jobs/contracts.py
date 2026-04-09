from __future__ import annotations

from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field


FetchStep = Literal[
    "spaces",
    "apps",
    "data-connections",
    "reloads",
    "audits",
    "licenses-consumption",
    "licenses-status",
    "app-data-metadata",
    "scripts",
    "lineage",
    "app-edges",
    "usage",
]

LineageGraphLevel = Literal["field", "table", "resource", "all"]

FETCH_STEP_ORDER: list[FetchStep] = [
    "spaces",
    "apps",
    "data-connections",
    "scripts",
    "lineage",
    "app-edges",
    "usage",
]

FETCH_STEP_ALL_ORDER: list[FetchStep] = [
    "spaces",
    "apps",
    "data-connections",
    "reloads",
    "audits",
    "licenses-consumption",
    "licenses-status",
    "app-data-metadata",
    "scripts",
    "lineage",
    "app-edges",
    "usage",
]

INDEPENDENT_FETCH_STEPS: set[FetchStep] = {
    "spaces",
    "apps",
    "data-connections",
    "reloads",
    "audits",
    "licenses-consumption",
    "licenses-status",
}


class FetchJobRequest(BaseModel):
    steps: list[FetchStep] | None = None
    limitApps: int | None = Field(default=None, ge=1)
    onlySpace: str | None = None
    clearOutputs: bool = False
    lineageConcurrency: int | None = Field(default=None, ge=1)
    lineageLevel: LineageGraphLevel = "resource"
    usageConcurrency: int | None = Field(default=None, ge=1)
    usageWindowDays: int | None = Field(default=None, ge=1)
    project_id: int


def _normalize_steps(steps: list[FetchStep] | None) -> list[FetchStep]:
    if not steps:
        return list(FETCH_STEP_ALL_ORDER)
    selected = set(steps)
    if "app-data-metadata" in selected:
        selected.add("apps")
    if "scripts" in selected:
        selected.add("apps")
    if "app-edges" in selected:
        selected.add("lineage")
    if "lineage" in selected or "usage" in selected:
        selected.add("apps")
    normalized = [step for step in FETCH_STEP_ALL_ORDER if step in selected]
    if not normalized:
        raise HTTPException(status_code=400, detail="no valid fetch steps supplied")
    return normalized
